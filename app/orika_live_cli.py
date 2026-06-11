#!/usr/bin/env python
"""Orika live CLI streamer.

Connects to the Orika binary protobuf WebSocket, logs in, subscribes/fetches the
requested streams, keeps the socket open, and writes live data to JSONL + CSV
snapshots.

Credentials are read from a local .env file or environment variables:
  ORIKA_WS_URL, ORIKA_LOGIN, ORIKA_PASSWORD, ORIKA_SERIAL_NO

Examples:
  uv run --with websocket-client --with protobuf python -u app/orika_live_cli.py --mode all --env-file .env
  uv run --with websocket-client --with protobuf python -u app/orika_live_cli.py --mode orders,deals --duration 60 --max-events 5
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

import websocket
from google.protobuf.json_format import MessageToDict

APP_DIR = Path(__file__).resolve().parent
GENERATED = APP_DIR / "generated"
sys.path.insert(0, str(GENERATED))

import clientmessage_pb2  # noqa: E402
import ClientpositionInsertandUpdate_pb2  # noqa: E402

DEFAULT_URL = "wss://auttrading.com:86"

ORDER_FIELDS = [
    "login", "time", "deal", "order", "symbol", "type", "volume", "price",
    "comment", "status", "select", "statustype", "subtype", "contraorder",
    "tradeexecutetime", "ourcomment", "orderstate",
]

DEAL_FIELDS = ["id", "time", "login", "symbol", "buysell", "volume", "price", "reason", "dealingtype"]

POSITION_FIELDS = [
    f.name
    for f in ClientpositionInsertandUpdate_pb2.ClientpositionInsertandUpdate.Insert.DESCRIPTOR.fields
]


def load_env(path: str | Path | None) -> None:
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def send_binary(ws: websocket.WebSocket, msg: Any) -> None:
    ws.send(msg.SerializeToString(), opcode=websocket.ABNF.OPCODE_BINARY)


def recv_proto(ws: websocket.WebSocket, timeout: float = 2.0) -> clientmessage_pb2.ClientMessage | str | None:
    old = ws.gettimeout()
    ws.settimeout(timeout)
    try:
        data = ws.recv()
    except Exception as exc:
        if "timed out" in str(exc).lower() or "timeout" in exc.__class__.__name__.lower():
            return None
        raise
    finally:
        ws.settimeout(old)
    if isinstance(data, str):
        return data
    msg = clientmessage_pb2.ClientMessage()
    msg.ParseFromString(data)
    return msg


def connect(url: str, skip_tls_verify: bool = True) -> websocket.WebSocket:
    sslopt = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False} if skip_tls_verify else {}
    return websocket.create_connection(url, sslopt=sslopt, timeout=30, skip_utf8_validation=True)


def login(ws: websocket.WebSocket, login_user: str, password: str, serial_no: str) -> str:
    msg = clientmessage_pb2.ClientMessage()
    msg.type = "login"
    msg.loginrequest.type = "login"
    msg.loginrequest.login = login_user
    msg.loginrequest.pwd = password
    msg.loginrequest.serialNo = serial_no or "*"
    send_binary(ws, msg)

    deadline = time.time() + 20
    while time.time() < deadline:
        resp = recv_proto(ws, max(1, min(5, deadline - time.time())))
        if resp is None or isinstance(resp, str):
            continue
        if resp.HasField("loginresponse"):
            return resp.loginresponse.status
    return "timeout"


def send_fetch_orders(ws: websocket.WebSocket) -> None:
    msg = clientmessage_pb2.ClientMessage()
    msg.type = "FETCH_ORDER_DATA"
    msg.fetchclientposition.type = "FETCH_ORDER_DATA"
    msg.fetchclientposition.action = "refresh"
    msg.fetchclientposition.time = 0
    send_binary(ws, msg)


def send_fetch_deals(ws: websocket.WebSocket) -> None:
    msg = clientmessage_pb2.ClientMessage()
    msg.type = "FETCH_DEALING_DATA"
    msg.fetchclientposition.type = "FETCH_DEALING_DATA"
    msg.fetchclientposition.action = "refresh"
    msg.fetchclientposition.time = 0
    send_binary(ws, msg)


def send_active_position_columns(ws: websocket.WebSocket, login_user: str) -> None:
    msg = clientmessage_pb2.ClientMessage()
    msg.type = "ACTIVE_COLUMNS_CHANGED"
    msg.activecolumnchagerequest.type = "ACTIVE_COLUMNS_CHANGED"
    msg.activecolumnchagerequest.requestType = "FETCH_CLIENT_POSITIONS"
    msg.activecolumnchagerequest.loginUser = login_user
    msg.activecolumnchagerequest.columns.append("ag-Grid-AutoColumn")
    msg.activecolumnchagerequest.columns.extend(POSITION_FIELDS)
    send_binary(ws, msg)


def send_fetch_positions(ws: websocket.WebSocket) -> None:
    msg = clientmessage_pb2.ClientMessage()
    msg.type = "FETCH_CLIENT_POSITIONS"
    msg.fetchclientposition.type = "FETCH_CLIENT_POSITIONS"
    msg.fetchclientposition.action = "refresh"
    msg.fetchclientposition.time = 0
    send_binary(ws, msg)


def row_dict(row_msg: Any) -> Dict[str, Any]:
    return MessageToDict(row_msg, preserving_proto_field_name=True)


def order_key(row: Dict[str, Any]) -> str:
    return str(row.get("order") or f"{row.get('login','')}:{row.get('symbol','')}:{row.get('time','')}:{row.get('price','')}")


def deal_key(row: Dict[str, Any]) -> str:
    return str(row.get("id") or f"{row.get('login','')}:{row.get('symbol','')}:{row.get('time','')}:{row.get('price','')}")


def position_key(row: Dict[str, Any]) -> str:
    return f"{row.get('login','')}:{row.get('symbol','')}"


def merge_non_empty(existing: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in update.items():
        if value not in (None, ""):
            existing[key] = value
    return existing


def write_jsonl(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON atomically so readers never see a partial live-memory file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    tmp.replace(path)


def build_state(
    *,
    status: str,
    modes: set[str],
    counts: Dict[str, int],
    orders: Dict[str, Dict[str, Any]],
    deals: Dict[str, Dict[str, Any]],
    positions: Dict[str, Dict[str, Any]],
    last_event: Dict[str, Any] | None,
    output_dir: Path,
    events_path: Path,
) -> Dict[str, Any]:
    """Return the current live in-memory state for external query processes.

    The dictionaries passed here are the process memory tables maintained by the
    WebSocket reader loop. Writing this file does not replace memory; it exposes
    a consistent copy to other CLIs/LLMs without requiring a second connection.
    """
    return {
        "success": True,
        "status": status,
        "updated_at": utc_now(),
        "last_event": last_event,
        "streams": sorted(modes),
        "counts": counts,
        "totals": {"orders": len(orders), "deals": len(deals), "positions": len(positions)},
        "source": {
            "connection": "Orika WebSocket binary protobuf",
            "memory_model": "insert replaces rows; update merges non-empty fields; delete removes keyed rows",
            "events_jsonl": str(events_path),
            "output_dir": str(output_dir),
        },
        "keys": {
            "orders": "order",
            "deals": "id or login:symbol:time:price fallback",
            "positions": "login:symbol",
        },
        "data": {"orders": orders, "deals": deals, "positions": positions},
    }


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], preferred_fields: list[str]) -> None:
    rows = list(rows)
    if not rows:
        return
    fields = []
    for f in preferred_fields:
        if any(f in r for r in rows):
            fields.append(f)
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_modes(text: str) -> set[str]:
    raw = {p.strip().lower() for p in text.split(",") if p.strip()}
    if "all" in raw:
        return {"orders", "deals", "positions"}
    allowed = {"orders", "deals", "positions"}
    unknown = raw - allowed
    if unknown:
        raise ValueError(f"Unknown mode(s): {', '.join(sorted(unknown))}")
    return raw or {"orders", "deals"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Orika live CLI streamer")
    parser.add_argument("--mode", default=os.getenv("ORIKA_STREAM_MODE", "all"), help="orders,deals,positions,all")
    parser.add_argument("--env-file", default=os.getenv("ORIKA_ENV_FILE", ".env"), help="Path to .env containing Orika credentials")
    parser.add_argument("--output-dir", default=os.getenv("ORIKA_OUTPUT_DIR", "orika_live_output"), help="Directory for JSONL/CSV/state output")
    parser.add_argument("--state-file", default=os.getenv("ORIKA_STATE_FILE", ""), help="Optional explicit state.json path. Default: <output-dir>/state.json")
    parser.add_argument("--snapshot-interval", type=int, default=int(os.getenv("ORIKA_SNAPSHOT_INTERVAL", "300")), help="CSV/state snapshot interval seconds")
    parser.add_argument("--duration", type=int, default=int(os.getenv("ORIKA_STREAM_DURATION", "0")), help="Stop after N seconds; 0 means run forever")
    parser.add_argument("--max-events", type=int, default=int(os.getenv("ORIKA_MAX_EVENTS", "0")), help="Stop after N data events; 0 means no limit")
    parser.add_argument("--skip-tls-verify", action="store_true", default=os.getenv("ORIKA_SKIP_TLS_VERIFY", "1") != "0")
    args = parser.parse_args()

    load_env(args.env_file)
    modes = parse_modes(args.mode)
    url = os.getenv("ORIKA_WS_URL", DEFAULT_URL)
    login_user = os.getenv("ORIKA_LOGIN", "")
    password = os.getenv("ORIKA_PASSWORD", "")
    serial_no = os.getenv("ORIKA_SERIAL_NO", "*")
    if not login_user or not password:
        print(json.dumps({"event": "error", "message": "ORIKA_LOGIN and ORIKA_PASSWORD required via .env or environment"}), flush=True)
        return 2

    out_dir = Path(args.output_dir)
    events_path = out_dir / "events.jsonl"
    state_path = Path(args.state_file) if args.state_file else out_dir / "state.json"
    status = {"event": "status", "message": f"connecting to {url}", "time": utc_now(), "modes": sorted(modes)}
    print(json.dumps(status), flush=True)
    write_jsonl(events_path, status)

    orders: Dict[str, Dict[str, Any]] = {}
    deals: Dict[str, Dict[str, Any]] = {}
    positions: Dict[str, Dict[str, Any]] = {}
    counts = {"orders": 0, "deals": 0, "positions": 0, "server_messages": 0, "unknown": 0}
    write_json_atomic(
        state_path,
        build_state(
            status="connecting",
            modes=modes,
            counts=counts,
            orders=orders,
            deals=deals,
            positions=positions,
            last_event=status,
            output_dir=out_dir,
            events_path=events_path,
        ),
    )
    last_snapshot = 0.0
    event_count = 0
    started = time.time()

    ws = connect(url, skip_tls_verify=args.skip_tls_verify)
    try:
        def flush_live_state(last_event: Dict[str, Any] | None, status_value: str = "live") -> None:
            if orders:
                write_csv(out_dir / "orders_snapshot.csv", orders.values(), ORDER_FIELDS)
            if deals:
                write_csv(out_dir / "deals_snapshot.csv", deals.values(), DEAL_FIELDS)
            if positions:
                write_csv(out_dir / "positions_snapshot.csv", positions.values(), POSITION_FIELDS)
            write_json_atomic(
                state_path,
                build_state(
                    status=status_value,
                    modes=modes,
                    counts=counts,
                    orders=orders,
                    deals=deals,
                    positions=positions,
                    last_event=last_event,
                    output_dir=out_dir,
                    events_path=events_path,
                ),
            )

        login_status = login(ws, login_user, password, serial_no)
        event = {"event": "login_status", "status": login_status, "time": utc_now()}
        print(json.dumps(event), flush=True)
        write_jsonl(events_path, event)
        flush_live_state(event, "logged_in")
        if login_status.lower() != "success":
            return 1

        if "positions" in modes:
            send_active_position_columns(ws, login_user)
            send_fetch_positions(ws)
            event = {"event": "subscribed", "stream": "positions", "request": "FETCH_CLIENT_POSITIONS", "time": utc_now()}
            print(json.dumps(event), flush=True)
            write_jsonl(events_path, event)
        if "orders" in modes:
            send_fetch_orders(ws)
            event = {"event": "subscribed", "stream": "orders", "request": "FETCH_ORDER_DATA", "time": utc_now()}
            print(json.dumps(event), flush=True)
            write_jsonl(events_path, event)
        if "deals" in modes:
            send_fetch_deals(ws)
            event = {"event": "subscribed", "stream": "deals", "request": "FETCH_DEALING_DATA", "time": utc_now()}
            print(json.dumps(event), flush=True)
            write_jsonl(events_path, event)

        while True:
            now = time.time()
            if args.duration and now - started >= args.duration:
                break
            if args.max_events and event_count >= args.max_events:
                break

            msg = recv_proto(ws, 2)
            if msg is None:
                continue
            if isinstance(msg, str):
                event = {"event": "text", "message": msg[:1000], "time": utc_now()}
                print(json.dumps(event, ensure_ascii=False), flush=True)
                write_jsonl(events_path, event)
                continue

            if msg.HasField("orderdata"):
                upserts, deletes = [], []
                for row_msg in msg.orderdata.insert:
                    row = row_dict(row_msg)
                    key = order_key(row)
                    row["id"] = key
                    orders[key] = row
                    upserts.append(row)
                for row_msg in msg.orderdata.update:
                    row = row_dict(row_msg)
                    key = order_key(row)
                    row["id"] = key
                    orders[key] = merge_non_empty(orders.get(key, {"id": key}), row)
                    upserts.append(orders[key])
                for row_msg in msg.orderdata.delete:
                    row = row_dict(row_msg)
                    key = order_key(row)
                    if key in orders:
                        orders.pop(key, None)
                    deletes.append(key)
                counts["orders"] += len(upserts)
                event_count += len(upserts) + len(deletes)
                event = {"event": "orders", "time": utc_now(), "upserts": upserts, "deletes": deletes, "total": len(orders)}
                print(json.dumps({k: v for k, v in event.items() if k != "upserts"} | {"upsert_count": len(upserts)}, ensure_ascii=False), flush=True)
                write_jsonl(events_path, event)
                flush_live_state(event)

            elif msg.HasField("dealingdata"):
                row = row_dict(msg.dealingdata)
                key = deal_key(row)
                row["id"] = key
                deals[key] = merge_non_empty(deals.get(key, {"id": key}), row)
                counts["deals"] += 1
                event_count += 1
                event = {"event": "deal", "time": utc_now(), "row": deals[key], "total": len(deals)}
                print(json.dumps({"event": "deal", "time": event["time"], "id": key, "total": len(deals)}, ensure_ascii=False), flush=True)
                write_jsonl(events_path, event)
                flush_live_state(event)

            elif msg.HasField("clientposition"):
                upserts = []
                for row_msg in msg.clientposition.insert:
                    row = row_dict(row_msg)
                    key = position_key(row)
                    row["id"] = key
                    positions[key] = row
                    upserts.append(row)
                for row_msg in msg.clientposition.update:
                    row = row_dict(row_msg)
                    key = position_key(row)
                    row["id"] = key
                    positions[key] = merge_non_empty(positions.get(key, {"id": key}), row)
                    upserts.append(positions[key])
                counts["positions"] += len(upserts)
                event_count += len(upserts)
                event = {"event": "positions", "time": utc_now(), "upserts": upserts, "total": len(positions)}
                print(json.dumps({"event": "positions", "time": event["time"], "upsert_count": len(upserts), "total": len(positions)}, ensure_ascii=False), flush=True)
                write_jsonl(events_path, event)
                flush_live_state(event)

            elif msg.HasField("servermessage"):
                counts["server_messages"] += 1
                event = {"event": "server_message", "time": utc_now(), "message": MessageToDict(msg.servermessage, preserving_proto_field_name=True)}
                print(json.dumps(event, ensure_ascii=False), flush=True)
                write_jsonl(events_path, event)
                flush_live_state(event)
            else:
                counts["unknown"] += 1
                event = {"event": "unknown", "time": utc_now(), "type": msg.type, "fields": [f.name for f, _ in msg.ListFields()]}
                print(json.dumps(event, ensure_ascii=False), flush=True)
                write_jsonl(events_path, event)
                flush_live_state(event)

            if args.snapshot_interval > 0 and time.time() - last_snapshot >= args.snapshot_interval:
                flush_live_state(event)
                last_snapshot = time.time()

    finally:
        summary = {
            "event": "summary",
            "time": utc_now(),
            "counts": counts,
            "totals": {"orders": len(orders), "deals": len(deals), "positions": len(positions)},
            "output_dir": str(out_dir),
            "events_jsonl": str(events_path),
        }
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        write_jsonl(events_path, summary)
        try:
            flush_live_state(summary, "stopped")
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
