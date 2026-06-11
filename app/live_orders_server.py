#!/usr/bin/env python
"""Simple Orika live orders web dashboard server.

Run:
  uv run --with aiohttp --with websocket-client --with protobuf python -u live_orders_server.py

Then open:
  http://127.0.0.1:8080

Credentials are supplied from the browser login form and are never written to disk.
"""
import asyncio
import json
import os
import ssl
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, Tuple

from aiohttp import web, WSMsgType
from google.protobuf.json_format import MessageToDict
import websocket

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"
if not GENERATED.exists():
    raise SystemExit("generated/ protobuf bindings not found. Generate them before running this server.")
sys.path.insert(0, str(GENERATED))

import clientmessage_pb2  # noqa: E402

ORIKA_DEFAULT_URL = os.getenv("ORIKA_WS_URL", "wss://auttrading.com:86")
HTML_PATH = ROOT / "live_orders.html"
DEALS_HTML_PATH = ROOT / "live_deals.html"

ORDER_FIELDS = [
    "login", "time", "deal", "order", "symbol", "type", "volume", "price",
    "comment", "status", "select", "statustype", "subtype", "contraorder",
    "tradeexecutetime", "ourcomment", "orderstate",
]

DEAL_FIELDS = [
    "id", "time", "login", "symbol", "buysell", "volume", "price", "reason", "dealingtype"
]


def _send_orika(ws: websocket.WebSocket, msg: Any) -> None:
    ws.send(msg.SerializeToString(), opcode=websocket.ABNF.OPCODE_BINARY)


def _order_key(row: Dict[str, Any]) -> str:
    order = row.get("order")
    if order not in (None, ""):
        return str(order)
    return f"{row.get('login','')}:{row.get('symbol','')}:{row.get('time','')}:{row.get('price','')}"


def _row_from_proto(row_msg: Any) -> Dict[str, Any]:
    row = MessageToDict(row_msg, preserving_proto_field_name=True)
    if "order" in row:
        row["id"] = str(row["order"])
    else:
        row["id"] = _order_key(row)
    return row


class OrikaOrderWorker:
    def __init__(self, browser_ws: web.WebSocketResponse, credentials: Dict[str, Any]):
        self.browser_ws = browser_ws
        self.credentials = credentials
        self.out: "Queue[Dict[str, Any]]" = Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="orika-order-worker", daemon=True)
        self.rows: Dict[str, Dict[str, Any]] = {}

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _emit(self, event: Dict[str, Any]) -> None:
        self.out.put(event)

    def _login(self, ws: websocket.WebSocket, login: str, password: str, serial_no: str) -> None:
        msg = clientmessage_pb2.ClientMessage()
        msg.type = "login"
        msg.loginrequest.type = "login"
        msg.loginrequest.login = login
        msg.loginrequest.pwd = password
        msg.loginrequest.serialNo = serial_no or "*"
        _send_orika(ws, msg)

        deadline = time.time() + 20
        while time.time() < deadline and not self.stop_event.is_set():
            old_timeout = ws.gettimeout()
            ws.settimeout(max(1, int(deadline - time.time())))
            try:
                data = ws.recv()
            finally:
                ws.settimeout(old_timeout)
            if isinstance(data, str):
                continue
            resp = clientmessage_pb2.ClientMessage()
            resp.ParseFromString(data)
            if resp.HasField("loginresponse"):
                status = resp.loginresponse.status
                self._emit({"event": "login_status", "status": status})
                if status.lower() == "success":
                    return
                raise RuntimeError(f"Login failed: {status}")
        raise RuntimeError("Login timed out")

    def _fetch_orders(self, ws: websocket.WebSocket) -> None:
        msg = clientmessage_pb2.ClientMessage()
        msg.type = "FETCH_ORDER_DATA"
        msg.fetchclientposition.type = "FETCH_ORDER_DATA"
        msg.fetchclientposition.action = "refresh"
        msg.fetchclientposition.time = 0
        _send_orika(ws, msg)
        self._emit({"event": "subscribed", "request": "FETCH_ORDER_DATA"})

    def _handle_orderdata(self, orderdata: Any) -> None:
        upserts = []
        deletes = []

        for row_msg in orderdata.insert:
            row = _row_from_proto(row_msg)
            key = row["id"]
            self.rows[key] = row
            upserts.append(row)

        for row_msg in orderdata.update:
            row = _row_from_proto(row_msg)
            key = row["id"]
            existing = self.rows.get(key, {"id": key})
            for k, v in row.items():
                if v not in (None, ""):
                    existing[k] = v
            self.rows[key] = existing
            upserts.append(existing)

        for del_msg in orderdata.delete:
            row = MessageToDict(del_msg, preserving_proto_field_name=True)
            key = str(row.get("order", ""))
            if key:
                self.rows.pop(key, None)
                deletes.append(key)

        if upserts or deletes:
            self._emit({
                "event": "orders",
                "upserts": upserts,
                "deletes": deletes,
                "total": len(self.rows),
            })

    def _run(self) -> None:
        url = self.credentials.get("url") or ORIKA_DEFAULT_URL
        login = self.credentials.get("login") or ""
        password = self.credentials.get("password") or ""
        serial_no = self.credentials.get("serialNo") or "*"

        if not login or not password:
            self._emit({"event": "error", "message": "Login and password are required"})
            return

        try:
            self._emit({"event": "status", "message": f"Connecting to {url}"})
            ws = websocket.create_connection(
                url,
                sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False},
                timeout=30,
                skip_utf8_validation=True,
            )
            try:
                self._emit({"event": "status", "message": "Connected. Logging in..."})
                self._login(ws, login, password, serial_no)
                self._fetch_orders(ws)
                self._emit({"event": "status", "message": "Live order stream running"})

                while not self.stop_event.is_set():
                    try:
                        old_timeout = ws.gettimeout()
                        ws.settimeout(2)
                        try:
                            data = ws.recv()
                        finally:
                            ws.settimeout(old_timeout)
                    except Exception as exc:
                        # websocket-client raises timeout exceptions during idle periods; keep reading.
                        if "timed out" in str(exc).lower() or "timeout" in exc.__class__.__name__.lower():
                            continue
                        raise
                    if isinstance(data, str):
                        self._emit({"event": "text", "message": data[:500]})
                        continue
                    msg = clientmessage_pb2.ClientMessage()
                    msg.ParseFromString(data)
                    if msg.HasField("orderdata"):
                        self._handle_orderdata(msg.orderdata)
                    elif msg.HasField("servermessage"):
                        self._emit({
                            "event": "server_message",
                            "message": MessageToDict(msg.servermessage, preserving_proto_field_name=True),
                        })
            finally:
                try:
                    ws.close()
                except Exception:
                    pass
        except Exception as exc:
            self._emit({"event": "error", "message": str(exc)})
        finally:
            self._emit({"event": "closed"})


class OrikaDealWorker(OrikaOrderWorker):
    """Live dealing-data stream worker.

    Orika's live deal stream does not always send an initial snapshot. It may stay
    quiet until a new deal happens. When `DEALING_DATA` messages arrive, each
    message is upserted by its `id` field.
    """

    def __init__(self, browser_ws: web.WebSocketResponse, credentials: Dict[str, Any]):
        super().__init__(browser_ws, credentials)
        self.thread = threading.Thread(target=self._run, name="orika-deal-worker", daemon=True)

    def _fetch_deals(self, ws: websocket.WebSocket) -> None:
        msg = clientmessage_pb2.ClientMessage()
        msg.type = "FETCH_DEALING_DATA"
        msg.fetchclientposition.type = "FETCH_DEALING_DATA"
        msg.fetchclientposition.action = "refresh"
        msg.fetchclientposition.time = 0
        _send_orika(ws, msg)
        self._emit({
            "event": "subscribed",
            "request": "FETCH_DEALING_DATA",
            "note": "Live deals may appear only when a new deal occurs; the server may not send an initial snapshot.",
        })

    def _handle_dealingdata(self, dealingdata: Any) -> None:
        row = MessageToDict(dealingdata, preserving_proto_field_name=True)
        key = str(row.get("id") or f"{row.get('login','')}:{row.get('symbol','')}:{row.get('time','')}:{row.get('price','')}")
        row["id"] = key
        existing = self.rows.get(key, {"id": key})
        for k, v in row.items():
            if v not in (None, ""):
                existing[k] = v
        self.rows[key] = existing
        self._emit({"event": "deals", "upserts": [existing], "deletes": [], "total": len(self.rows)})

    def _run(self) -> None:
        url = self.credentials.get("url") or ORIKA_DEFAULT_URL
        login = self.credentials.get("login") or ""
        password = self.credentials.get("password") or ""
        serial_no = self.credentials.get("serialNo") or "*"

        if not login or not password:
            self._emit({"event": "error", "message": "Login and password are required"})
            return

        try:
            self._emit({"event": "status", "message": f"Connecting to {url}"})
            ws = websocket.create_connection(
                url,
                sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False},
                timeout=30,
                skip_utf8_validation=True,
            )
            try:
                self._emit({"event": "status", "message": "Connected. Logging in..."})
                self._login(ws, login, password, serial_no)
                self._fetch_deals(ws)
                self._emit({"event": "status", "message": "Live deal stream running; waiting for DEALING_DATA messages"})

                while not self.stop_event.is_set():
                    try:
                        old_timeout = ws.gettimeout()
                        ws.settimeout(2)
                        try:
                            data = ws.recv()
                        finally:
                            ws.settimeout(old_timeout)
                    except Exception as exc:
                        if "timed out" in str(exc).lower() or "timeout" in exc.__class__.__name__.lower():
                            continue
                        raise
                    if isinstance(data, str):
                        self._emit({"event": "text", "message": data[:500]})
                        continue
                    msg = clientmessage_pb2.ClientMessage()
                    msg.ParseFromString(data)
                    if msg.HasField("dealingdata"):
                        self._handle_dealingdata(msg.dealingdata)
                    elif msg.HasField("servermessage"):
                        self._emit({"event": "server_message", "message": MessageToDict(msg.servermessage, preserving_proto_field_name=True)})
                    else:
                        self._emit({"event": "debug", "message": f"Received {msg.type or 'unknown'}; fields={[f.name for f, _ in msg.ListFields()]}"})
            finally:
                try:
                    ws.close()
                except Exception:
                    pass
        except Exception as exc:
            self._emit({"event": "error", "message": str(exc)})
        finally:
            self._emit({"event": "closed"})


async def index(_: web.Request) -> web.Response:
    return web.FileResponse(HTML_PATH)


async def deals_page(_: web.Request) -> web.Response:
    return web.FileResponse(DEALS_HTML_PATH)


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "orika-live-orders-deals", "defaultUrl": ORIKA_DEFAULT_URL})


async def _ws_stream(request: web.Request, worker_cls: Any) -> web.WebSocketResponse:
    browser_ws = web.WebSocketResponse(max_msg_size=1024 * 1024)
    await browser_ws.prepare(request)

    worker = None
    pump_task = None

    async def pump_events(active_worker: OrikaOrderWorker) -> None:
        try:
            while not active_worker.stop_event.is_set():
                try:
                    event = await asyncio.to_thread(active_worker.out.get, True, 0.5)
                except Empty:
                    continue
                await browser_ws.send_str(json.dumps(event, ensure_ascii=False))
                if event.get("event") == "closed":
                    break
        except Exception:
            active_worker.stop()

    try:
        async for msg in browser_ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    await browser_ws.send_json({"event": "error", "message": "Invalid JSON"})
                    continue

                if payload.get("action") == "connect":
                    if worker:
                        worker.stop()
                    worker = worker_cls(browser_ws, payload)
                    worker.start()
                    pump_task = asyncio.create_task(pump_events(worker))
                elif payload.get("action") == "disconnect":
                    if worker:
                        worker.stop()
                    await browser_ws.send_json({"event": "status", "message": "Disconnect requested"})
                else:
                    await browser_ws.send_json({"event": "error", "message": "Unknown action"})
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        if worker:
            worker.stop()
        if pump_task:
            pump_task.cancel()
    return browser_ws


async def ws_orders(request: web.Request) -> web.WebSocketResponse:
    return await _ws_stream(request, OrikaOrderWorker)


async def ws_deals(request: web.Request) -> web.WebSocketResponse:
    return await _ws_stream(request, OrikaDealWorker)


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/deals", deals_page)
    app.router.add_get("/health", health)
    app.router.add_get("/ws/orders", ws_orders)
    app.router.add_get("/ws/deals", ws_deals)
    return app


if __name__ == "__main__":
    port = int(os.getenv("LIVE_ORDERS_PORT", "8080"))
    print(f"Orika live orders dashboard: http://127.0.0.1:{port}")
    web.run_app(make_app(), host="127.0.0.1", port=port)
