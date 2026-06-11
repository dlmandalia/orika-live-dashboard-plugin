"""Tool schemas for the Orika live dashboard plugin."""

START_SCHEMA = {
    "name": "orika_dashboard_start",
    "description": (
        "Start the local Orika live orders/deals dashboard server. "
        "The dashboard opens in a browser at http://127.0.0.1:<port>/ for orders "
        "and /deals for live deals. Credentials are entered in the browser and are not saved."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "port": {
                "type": "integer",
                "description": "Local port for the dashboard server. Default: 8080.",
                "default": 8080,
            },
            "orika_ws_url": {
                "type": "string",
                "description": "Default Orika WebSocket URL shown in the page. Default: wss://auttrading.com:86.",
                "default": "wss://auttrading.com:86",
            },
        },
        "required": [],
    },
}

STATUS_SCHEMA = {
    "name": "orika_dashboard_status",
    "description": "Check if the local Orika dashboard server is running and return the orders/deals URLs.",
    "parameters": {
        "type": "object",
        "properties": {
            "port": {"type": "integer", "description": "Local dashboard port. Default: 8080.", "default": 8080},
        },
        "required": [],
    },
}

STOP_SCHEMA = {
    "name": "orika_dashboard_stop",
    "description": "Stop the local Orika dashboard server started by orika_dashboard_start.",
    "parameters": {
        "type": "object",
        "properties": {
            "port": {"type": "integer", "description": "Local dashboard port. Default: 8080.", "default": 8080},
        },
        "required": [],
    },
}
