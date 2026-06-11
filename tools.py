"""Runtime tool handlers for the Orika CLI live data plugin.

These tools manage a background CLI streamer. They never accept or store Orika
credentials directly. Credentials must live in the user's local .env file.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
APP_DIR = PLUGIN_DIR / "app"
RUNTIME_DIR = PLUGIN_DIR / ".runtime"
STREAM_SCRIPT = APP_DIR / "orika_live_cli.py"
PID_FILE = RUNTIME_DIR / "orika-stream.pid"
META_FILE = RUNTIME_DIR / "orika-stream.json"
LOG_FILE = RUNTIME_DIR / "orika-stream.log"


def _json(**data) -> str:
    return json.dumps(data, ensure_ascii=False)


def _ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _process_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=5)
            return str(pid) in (result.stdout or "")
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _read_meta() -> dict:
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _tail(path: Path, chars: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[-chars:]
    except Exception:
        return ""


def start_stream(args: dict, **kwargs) -> str:
    del kwargs
    _ensure_runtime()
    existing_pid = _read_pid()
    if _process_running(existing_pid):
        return _json(success=True, already_running=True, pid=existing_pid, meta=_read_meta(), log=str(LOG_FILE))

    if not STREAM_SCRIPT.exists():
        return _json(success=False, error=f"Missing CLI streamer: {STREAM_SCRIPT}")

    uv = shutil.which("uv")
    if not uv:
        return _json(success=False, error="uv is required. Install uv, then retry.")

    mode = args.get("mode") or "all"
    env_file = args.get("env_file") or ".env"
    output_dir = args.get("output_dir") or "orika_live_output"
    snapshot_interval = int(args.get("snapshot_interval") or 300)
    duration = int(args.get("duration") or 0)

    env_path = Path(env_file)
    if not env_path.is_absolute():
        env_path = Path.cwd() / env_path
    out_path = Path(output_dir)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path

    cmd = [
        uv,
        "run",
        "--with", "websocket-client",
        "--with", "protobuf",
        "python",
        "-u",
        str(STREAM_SCRIPT),
        "--mode", str(mode),
        "--env-file", str(env_path),
        "--output-dir", str(out_path),
        "--snapshot-interval", str(snapshot_interval),
    ]
    if duration:
        cmd.extend(["--duration", str(duration)])

    log_fh = LOG_FILE.open("a", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd,
        cwd=str(PLUGIN_DIR),
        env=os.environ.copy(),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    meta = {
        "pid": proc.pid,
        "mode": mode,
        "env_file": str(env_path),
        "output_dir": str(out_path),
        "events_jsonl": str(out_path / "events.jsonl"),
        "orders_csv": str(out_path / "orders_snapshot.csv"),
        "deals_csv": str(out_path / "deals_snapshot.csv"),
        "positions_csv": str(out_path / "positions_snapshot.csv"),
        "snapshot_interval": snapshot_interval,
        "duration": duration,
        "log": str(LOG_FILE),
        "started_at": time.time(),
    }
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Give it a moment to fail fast if credentials/deps are wrong.
    time.sleep(2)
    if proc.poll() is not None:
        return _json(success=False, error=f"Stream exited with code {proc.returncode}", log=str(LOG_FILE), log_tail=_tail(LOG_FILE), meta=meta)
    return _json(success=True, started=True, pid=proc.pid, meta=meta)


def status_stream(args: dict, **kwargs) -> str:
    del args, kwargs
    pid = _read_pid()
    meta = _read_meta()
    running = _process_running(pid)
    output_dir = Path(meta.get("output_dir", "")) if meta.get("output_dir") else None
    files = {}
    if output_dir:
        for name in ["events.jsonl", "orders_snapshot.csv", "deals_snapshot.csv", "positions_snapshot.csv"]:
            p = output_dir / name
            files[name] = {"path": str(p), "exists": p.exists(), "bytes": p.stat().st_size if p.exists() else 0}
    return _json(success=True, running=running, pid=pid, meta=meta, files=files, log=str(LOG_FILE), log_tail=_tail(LOG_FILE, 2000))


def stop_stream(args: dict, **kwargs) -> str:
    del args, kwargs
    pid = _read_pid()
    if not pid:
        return _json(success=True, stopped=False, message="No stream pid file found")
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True, text=True, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        try:
            PID_FILE.unlink()
        except FileNotFoundError:
            pass
        return _json(success=True, stopped=True, pid=pid, meta=_read_meta())
    except Exception as exc:
        return _json(success=False, error=str(exc), pid=pid)
