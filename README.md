# Orika Live Dashboard Plugin

Hermes plugin + standalone web app for the verified Orika live dashboard.

It provides:

- Live Orders page using AG Grid: `http://127.0.0.1:8080/`
- Live Deals page using AG Grid: `http://127.0.0.1:8080/deals`
- A local Python WebSocket proxy that connects to Orika using binary protobuf frames
- Hermes plugin tools to start/status/stop the dashboard

Credentials are never committed and are not stored by the app. The browser asks the user for username/password/serial number for each session.

## Install as a Hermes plugin

After this repo is on GitHub:

```bash
hermes plugins install OWNER/REPO --enable
```

or with a full URL:

```bash
hermes plugins install https://github.com/OWNER/REPO.git --enable
```

Restart Hermes after enabling the plugin. Then ask Hermes:

```text
Start the Orika dashboard
```

The plugin exposes these tools:

- `orika_dashboard_start`
- `orika_dashboard_status`
- `orika_dashboard_stop`

## Run manually without Hermes

From this repository root:

```bash
cd app
uv run --with aiohttp --with websocket-client --with protobuf python -u live_orders_server.py
```

Open:

```text
http://127.0.0.1:8080/
http://127.0.0.1:8080/deals
```

## What was verified

This package was created from the working Orika dashboard in `C:\\Hermes\\Oreka`.

Verified behavior before packaging:

- Orika WebSocket login succeeds
- `FETCH_ORDER_DATA` receives order rows and live updates
- `FETCH_DEALING_DATA` receives live deal rows
- Browser dashboard endpoint streams rows into AG Grid
- The deals endpoint received 2 live deal rows during the latest test window

Verified after packaging:

- `python scripts/smoke.py` passes
- Plugin start/status/stop handlers successfully launched the packaged app on port 8090
- Hermes installed the plugin from a local Git URL into a temporary `HERMES_HOME`
- `hermes plugins list --user` showed `orika-live-dashboard` as enabled

## Files

```text
plugin.yaml                Hermes plugin manifest
__init__.py                Registers Hermes tools
schemas.py                 Tool schemas shown to Hermes
tools.py                   Tool handlers to start/status/stop dashboard
app/live_orders_server.py  Local web server + Orika WebSocket proxy
app/live_orders.html       AG Grid live orders page
app/live_deals.html        AG Grid live deals page
app/generated/*.py         Generated Orika protobuf bindings
```

## Security

Do not commit credentials. Do not add `.env` with real values. The `.gitignore` excludes `.env`, runtime logs, caches, CSV exports, and pyc files.

If deploying beyond localhost, add HTTPS, authentication, and network restrictions before exposing it.
