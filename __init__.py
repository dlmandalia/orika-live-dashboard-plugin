"""Hermes plugin for Orika CLI live orders/deals/positions streaming."""
from __future__ import annotations

try:
    from .schemas import START_SCHEMA, STATUS_SCHEMA, STOP_SCHEMA
    from .tools import start_stream, status_stream, stop_stream
except ImportError:  # pragma: no cover - loader compatibility fallback
    from schemas import START_SCHEMA, STATUS_SCHEMA, STOP_SCHEMA
    from tools import start_stream, status_stream, stop_stream


def register(ctx) -> None:
    ctx.register_tool(
        name="orika_stream_start",
        toolset="orika_live_data",
        schema=START_SCHEMA,
        handler=start_stream,
        description="Start the Orika CLI live data stream for orders, deals, and positions.",
        emoji="📡",
    )
    ctx.register_tool(
        name="orika_stream_status",
        toolset="orika_live_data",
        schema=STATUS_SCHEMA,
        handler=status_stream,
        description="Check Orika CLI live stream status and output paths.",
        emoji="🩺",
    )
    ctx.register_tool(
        name="orika_stream_stop",
        toolset="orika_live_data",
        schema=STOP_SCHEMA,
        handler=stop_stream,
        description="Stop the Orika CLI live stream.",
        emoji="🛑",
    )
