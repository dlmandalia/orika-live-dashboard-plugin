# Orika Live Data CLI Plugin

Hermes plugin + standalone CLI streamer for Orika live data.

This is the main supported flow:

- connect to Orika WebSocket
- login using credentials from a local `.env`
- keep the socket open
- stream live orders, deals, and positions
- write `events.jsonl` plus CSV snapshots

The old AG Grid HTML files remain under `app/` only as optional/manual viewing helpers. They are not the plugin interface.

## Install as a Hermes plugin

```bash
hermes plugins install dlmandalia/orika-live-dashboard-plugin --enable
```

Restart Hermes / start a new Hermes session after enabling.

The plugin exposes these tools:

- `orika_stream_start`
- `orika_stream_status`
- `orika_stream_stop`

Ask Hermes:

```text
Start the Orika live stream using .env and write all data to orika_live_output
```

## Required local `.env`

Create a local `.env` where the stream is started. Do not commit this file.

```dotenv
ORIKA_WS_URL=wss://auttrading.com:86
ORIKA_LOGIN=<your-login>
ORIKA_PASSWORD=<your-password>
ORIKA_SERIAL_NO=*
```

Credentials are read from `.env` at runtime only. They are not stored in the plugin or written to output files.

## Run manually without Hermes

From this repository root:

```bash
uv run --with websocket-client --with protobuf python -u app/orika_live_cli.py \
  --mode all \
  --env-file .env \
  --output-dir orika_live_output \
  --snapshot-interval 300
```

Modes:

```text
orders
orders,deals
positions
all
```

Useful test command:

```bash
uv run --with websocket-client --with protobuf python -u app/orika_live_cli.py \
  --mode orders,deals \
  --env-file C:/Hermes/Oreka/.env \
  --output-dir test_output \
  --duration 30 \
  --max-events 2
```

## Output files

Default output directory:

```text
orika_live_output/
```

Files:

```text
events.jsonl             append-only live event log
orders_snapshot.csv      latest merged order table
deals_snapshot.csv       latest merged deal table
positions_snapshot.csv   latest merged positions table
```

`events.jsonl` contains full event data. CSV snapshot files are rewritten every `--snapshot-interval` seconds and again on clean shutdown.

## What the stream sends

Orders:

```text
ClientMessage.type = FETCH_ORDER_DATA
fetchclientposition.type = FETCH_ORDER_DATA
fetchclientposition.action = refresh
fetchclientposition.time = 0
```

Deals:

```text
ClientMessage.type = FETCH_DEALING_DATA
fetchclientposition.type = FETCH_DEALING_DATA
fetchclientposition.action = refresh
fetchclientposition.time = 0
```

Positions:

```text
ACTIVE_COLUMNS_CHANGED for FETCH_CLIENT_POSITIONS
FETCH_CLIENT_POSITIONS refresh
```

## Verified

Before this CLI packaging, live connectivity was verified:

- Orika WebSocket login succeeds
- `FETCH_ORDER_DATA` receives order rows and live updates
- `FETCH_DEALING_DATA` receives live deal rows
- `FETCH_CLIENT_POSITIONS` receives live position data after active-column subscription

After plugin packaging:

- `python scripts/smoke.py` passes
- Hermes can install the plugin from GitHub
- The CLI streamer is the supported interface for other CLIs/agents

## Files

```text
plugin.yaml              Hermes plugin manifest
__init__.py              Registers Hermes tools
schemas.py               Tool schemas shown to Hermes
tools.py                 Tool handlers to start/status/stop CLI stream
app/orika_live_cli.py    Main CLI streamer
app/generated/*.py       Generated Orika protobuf bindings
```

## Security

Do not commit `.env` or real Orika credentials. This repository ignores `.env`, runtime logs, CSVs, output directories, and cache files.
