"""Hermes plugin for the Orika live orders/deals dashboard."""
from __future__ import annotations

try:
    from .schemas import START_SCHEMA, STATUS_SCHEMA, STOP_SCHEMA
    from .tools import start_dashboard, status_dashboard, stop_dashboard
except ImportError:  # pragma: no cover - loader compatibility fallback
    from schemas import START_SCHEMA, STATUS_SCHEMA, STOP_SCHEMA
    from tools import start_dashboard, status_dashboard, stop_dashboard


def register(ctx) -> None:
    ctx.register_tool(
        name="orika_dashboard_start",
        toolset="orika_dashboard",
        schema=START_SCHEMA,
        handler=start_dashboard,
        description="Start the local Orika live orders/deals AG Grid dashboard.",
        emoji="📈",
    )
    ctx.register_tool(
        name="orika_dashboard_status",
        toolset="orika_dashboard",
        schema=STATUS_SCHEMA,
        handler=status_dashboard,
        description="Check whether the local Orika dashboard server is running.",
        emoji="🩺",
    )
    ctx.register_tool(
        name="orika_dashboard_stop",
        toolset="orika_dashboard",
        schema=STOP_SCHEMA,
        handler=stop_dashboard,
        description="Stop the local Orika dashboard server started by the plugin.",
        emoji="🛑",
    )
