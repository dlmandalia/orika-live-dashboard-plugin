"""Tool schemas for the Orika CLI live data plugin."""

START_SCHEMA = {
    "name": "orika_stream_start",
    "description": (
        "Start a background Orika CLI live stream. The process connects to the Orika "
        "binary protobuf WebSocket, logs in from a local .env file, keeps the socket open, "
        "and writes live orders/deals/positions to JSONL plus CSV snapshots."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "description": "Comma-separated streams: orders,deals,positions,all. Default: all.",
                "default": "all",
            },
            "env_file": {
                "type": "string",
                "description": "Path to .env containing ORIKA_WS_URL, ORIKA_LOGIN, ORIKA_PASSWORD, ORIKA_SERIAL_NO. Default: .env in current working directory.",
                "default": ".env",
            },
            "output_dir": {
                "type": "string",
                "description": "Directory where events.jsonl and CSV snapshots are written. Default: orika_live_output.",
                "default": "orika_live_output",
            },
            "snapshot_interval": {
                "type": "integer",
                "description": "Seconds between CSV snapshot writes. Default: 300.",
                "default": 300,
            },
            "duration": {
                "type": "integer",
                "description": "Optional stop-after seconds. 0 means run forever. Default: 0.",
                "default": 0,
            },
        },
        "required": [],
    },
}

STATUS_SCHEMA = {
    "name": "orika_stream_status",
    "description": "Check whether the Orika CLI live stream process is running and where it writes data.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

STOP_SCHEMA = {
    "name": "orika_stream_stop",
    "description": "Stop the Orika CLI live stream process started by orika_stream_start.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
