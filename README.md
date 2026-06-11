# Orika Live Data CLI Plugin

Hermes plugin + standalone CLI streamer for Orika live data.

This is the main supported flow:

- connect to Orika WebSocket
- login using credentials from a local `.env`
- keep the socket open
- maintain live in-memory tables for orders, deals, and positions
- stream live orders, deals, and positions
- write `events.jsonl`, `state.json`, and CSV snapshots
- let other commands query `state.json` without opening another WebSocket

The old AG Grid HTML files remain under `app/` only as optional/manual viewing helpers. They are not the plugin interface.

## Install as a Hermes plugin

```bash
hermes plugins install dlmandalia/orika-live-dashboard-plugin --enable
```

Restart Hermes / start a new Hermes session after enabling.

The plugin exposes these tools:

- `orika_stream_start`
- `orika_stream_status`
- `orika_stream_query`
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
state.json               current live in-memory state for queries
orders_snapshot.csv      latest merged order table
deals_snapshot.csv       latest merged deal table
positions_snapshot.csv   latest merged positions table
```

`events.jsonl` contains full event data. `state.json` is written atomically and contains the current in-memory tables. CSV snapshot files are rewritten every `--snapshot-interval` seconds and again on clean shutdown.

## Query live memory without reconnecting

Once the stream is running, use the query tool or the CLI helper. This reads `state.json`; it does not create a second Orika WebSocket connection.

```text
orika_stream_query stream=summary
orika_stream_query stream=orders limit=20
orika_stream_query stream=positions key=LOGIN:SYMBOL
orika_stream_query stream=positions key=LOGIN:SYMBOL field=volume
```

Manual query helper:

```bash
python app/orika_query_state.py --state-file orika_live_output/state.json --stream summary
python app/orika_query_state.py --state-file orika_live_output/state.json --stream orders --limit 20
python app/orika_query_state.py --state-file orika_live_output/state.json --stream positions --key LOGIN:SYMBOL --field volume
```

## Live memory/event-management docs

For LLMs and other CLIs, read this file before generating commands:

```text
docs/LIVE_MEMORY_EVENT_SYSTEM.md
```

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
tools.py                 Tool handlers to start/status/query/stop CLI stream
app/orika_live_cli.py    Main CLI streamer; owns WebSocket and live memory
app/orika_query_state.py Query state.json without reconnecting
app/generated/*.py       Generated Orika protobuf bindings
docs/LIVE_MEMORY_EVENT_SYSTEM.md LLM/CLI guide for live memory and event management
```

## Security

Do not commit `.env` or real Orika credentials. This repository ignores `.env`, runtime logs, CSVs, output directories, and cache files.
