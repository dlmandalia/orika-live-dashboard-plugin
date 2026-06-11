"""Runtime tool handlers for the Orika live dashboard plugin.

The handlers intentionally do not accept or store Orika credentials. Users enter
credentials in the browser UI for each session.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PLUGIN_DIR = Path(__file__).resolve().parent
APP_DIR = PLUGIN_DIR / "app"
RUNTIME_DIR = PLUGIN_DIR / ".runtime"
SERVER_SCRIPT = APP_DIR / "live_orders_server.py"


def _json(**data) -> str:
    return json.dumps(data, ensure_ascii=False)


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", int(port))) == 0


def _health(port: int) -> dict:
    try:
        raw = urlopen(f"http://127.0.0.1:{int(port)}/health", timeout=2).read().decode("utf-8")
        return json.loads(raw)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _pidfile(port: int) -> Path:
    RUNTIME_DIR.mkdir(exist_ok=True)
    return RUNTIME_DIR / f"server-{int(port)}.pid"


def _logfile(port: int) -> Path:
    RUNTIME_DIR.mkdir(exist_ok=True)
    return RUNTIME_DIR / f"server-{int(port)}.log"


def _read_pid(port: int) -> int | None:
    p = _pidfile(port)
    if not p.exists():
        return None
    try:
        return int(p.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _process_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in (result.stdout or "")
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _urls(port: int) -> dict:
    base = f"http://127.0.0.1:{int(port)}"
    return {"orders_url": base + "/", "deals_url": base + "/deals", "health_url": base + "/health"}


def start_dashboard(args: dict, **kwargs) -> str:
    del kwargs
    port = int(args.get("port") or 8080)
    orika_ws_url = args.get("orika_ws_url") or os.getenv("ORIKA_WS_URL", "wss://auttrading.com:86")

    if not SERVER_SCRIPT.exists():
        return _json(success=False, error=f"Missing server script: {SERVER_SCRIPT}")

    if _port_open(port):
        health = _health(port)
        return _json(success=True, already_running=True, port=port, health=health, **_urls(port))

    uv = shutil.which("uv")
    if not uv:
        return _json(
            success=False,
            error="uv is required to launch the dashboard with isolated dependencies. Install uv or run the app manually with aiohttp/websocket-client/protobuf installed.",
        )

    log_path = _logfile(port)
    log = log_path.open("a", encoding="utf-8")
    env = os.environ.copy()
    env["LIVE_ORDERS_PORT"] = str(port)
    env["ORIKA_WS_URL"] = str(orika_ws_url)

    cmd = [
        uv,
        "run",
        "--with", "aiohttp",
        "--with", "websocket-client",
        "--with", "protobuf",
        "python",
        "-u",
        str(SERVER_SCRIPT),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        cmd,
        cwd=str(APP_DIR),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    _pidfile(port).write_text(str(proc.pid), encoding="utf-8")

    deadline = time.time() + 20
    health = {"ok": False, "error": "not checked"}
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = ""
            try:
                tail = log_path.read_text(encoding="utf-8", errors="ignore")[-2000:]
            except Exception:
                pass
            return _json(success=False, error=f"Dashboard exited with code {proc.returncode}", log=str(log_path), log_tail=tail)
        health = _health(port)
        if health.get("ok"):
            return _json(success=True, started=True, pid=proc.pid, port=port, log=str(log_path), health=health, **_urls(port))
        time.sleep(0.5)

    return _json(success=False, error="Dashboard did not become healthy within 20 seconds", pid=proc.pid, log=str(log_path), health=health)


def status_dashboard(args: dict, **kwargs) -> str:
    del kwargs
    port = int(args.get("port") or 8080)
    pid = _read_pid(port)
    health = _health(port)
    return _json(
        success=True,
        port=port,
        pid=pid,
        pid_running=_process_running(pid),
        port_open=_port_open(port),
        health=health,
        log=str(_logfile(port)),
        **_urls(port),
    )


def stop_dashboard(args: dict, **kwargs) -> str:
    del kwargs
    port = int(args.get("port") or 8080)
    pid = _read_pid(port)
    if not pid:
        return _json(success=True, stopped=False, message="No pid file found", port=port)
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True, text=True, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        try:
            _pidfile(port).unlink()
        except FileNotFoundError:
            pass
        return _json(success=True, stopped=True, pid=pid, port=port)
    except Exception as exc:
        return _json(success=False, error=str(exc), pid=pid, port=port)
