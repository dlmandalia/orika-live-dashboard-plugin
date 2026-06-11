# Orika Live Memory + Event Management System

This plugin is designed as a long-running live-memory service, not a one-shot fetcher.

The correct architecture is:

```text
one Orika WebSocket connection
        |
        v
binary protobuf ClientMessage reader loop
        |
        v
in-process memory tables
  - orders keyed by order
  - deals keyed by id, or login:symbol:time:price fallback
  - positions keyed by login:symbol
        |
        +--> append every server event to events.jsonl
        +--> atomically write current state to state.json
        +--> periodically write CSV snapshots
        +--> plugin/CLI query reads state.json without reconnecting
```

## Why this is needed

Orika sends an initial snapshot and then live deltas. A command should not reconnect every time it needs a value. Reconnecting loses the benefit of live subscriptions and may miss updates.

Start one stream process and keep it running. Every command/query should read from the stream's live memory snapshot (`state.json`) or event log (`events.jsonl`).

## Main commands for LLMs

Install:

```bash
hermes plugins install dlmandalia/orika-live-dashboard-plugin --enable
```

Start the stream:

```text
Use tool: orika_stream_start
Arguments:
{
  "mode": "all",
  "env_file": "C:/Hermes/Oreka/.env",
  "output_dir": "C:/Hermes/Oreka/orika_live_output",
  "snapshot_interval": 300
}
```

Check health/status:

```text
Use tool: orika_stream_status
```

Query current live memory summary:

```text
Use tool: orika_stream_query
Arguments: {"stream": "summary"}
```

Query latest orders from memory:

```text
Use tool: orika_stream_query
Arguments: {"stream": "orders", "limit": 20}
```

Query one position row:

```text
Use tool: orika_stream_query
Arguments: {"stream": "positions", "key": "LOGIN:SYMBOL"}
```

Query one field from one position row:

```text
Use tool: orika_stream_query
Arguments: {"stream": "positions", "key": "LOGIN:SYMBOL", "field": "volume"}
```

Filter rows from memory:

```text
Use tool: orika_stream_query
Arguments: {"stream": "orders", "field": "symbol", "equals": "XAUUSD", "limit": 50}
```

Stop the stream:

```text
Use tool: orika_stream_stop
```

## Manual CLI commands

Run live stream manually:

```bash
uv run --with websocket-client --with protobuf python -u app/orika_live_cli.py \
  --mode all \
  --env-file C:/Hermes/Oreka/.env \
  --output-dir C:/Hermes/Oreka/orika_live_output \
  --snapshot-interval 300
```

Query memory manually:

```bash
python app/orika_query_state.py \
  --state-file C:/Hermes/Oreka/orika_live_output/state.json \
  --stream summary
```

```bash
python app/orika_query_state.py \
  --state-file C:/Hermes/Oreka/orika_live_output/state.json \
  --stream orders \
  --limit 20
```

```bash
python app/orika_query_state.py \
  --state-file C:/Hermes/Oreka/orika_live_output/state.json \
  --stream positions \
  --key LOGIN:SYMBOL \
  --field volume
```

## Output files

```text
orika_live_output/events.jsonl             append-only event log
orika_live_output/state.json               current live memory snapshot
orika_live_output/orders_snapshot.csv      current orders table
orika_live_output/deals_snapshot.csv       current deals table
orika_live_output/positions_snapshot.csv   current positions table
```

`state.json` is written atomically. A reader should read it as a complete snapshot and not modify it.

## Memory update rules

Orders:

```text
ORDER_DATA.insert[]  -> set/replace row by order id
ORDER_DATA.update[]  -> merge fields into row by order id
ORDER_DATA.delete[]  -> remove row by order id
```

Deals:

```text
DEALING_DATA -> merge/set row by id
```

Positions:

```text
CLIENT_POSITION.insert[] -> set/replace row by login:symbol
CLIENT_POSITION.update[] -> merge fields into row by login:symbol
```

Do not treat updates as complete rows. They can be deltas. Merge non-empty fields into the existing row.

## Event-management pattern

A future event management system can consume either:

1. `events.jsonl` for every event/delta in order.
2. `state.json` for the latest current state.

Recommended pattern:

```text
if you need triggers/alerts/audit:
    tail events.jsonl

if you need latest answer/current dashboard/report:
    read state.json or CSV snapshot

if you need exact current field:
    orika_stream_query stream/key/field
```

Example event rules:

```text
on ORDER_DATA.insert where symbol == XAUUSD -> notify
on DEALING_DATA where volume > threshold -> notify
on CLIENT_POSITION.update where clientfloatingpl < -limit -> risk alert
```

Rules should not open a second WebSocket. They should consume the existing live memory/event output.

## Authoritative fallback source repo

If a CLI/LLM gets stuck, sees an internal error, protobuf mismatch, unknown message type, or cannot understand the server behavior from this plugin alone, it should inspect the original OrikaServer proto/source repository:

```text
https://github.com/abhishek43501/orikaserver_proto
```

Recommended fallback workflow:

```bash
git clone https://github.com/abhishek43501/orikaserver_proto.git
```

Then inspect:

```text
ProtoFile/clientmessage.proto
ProtoFile/loginrequest.proto
ProtoFile/loginresponse.proto
ProtoFile/FetchClientPositions.proto
ProtoFile/ActiveColumnChanged.proto
ProtoFile/ClientpositionInsertandUpdate.proto
ProtoFile/OrderData.proto
ProtoFile/DealingData.proto
OrikaServer/server/Server.cpp
OrikaServer/StaticClass.cpp
OrikaServer/Manager.cpp
OrikaServer/ProtoMessageConverter.cpp
```

Use that repo as the authoritative reference for protobuf envelope fields, request/response type names, and C++ server-side subscription behavior.

## C++ server evidence used

The developer-provided C++ source shows that these requests are long-lived server-side subscriptions/state flags, not one-shot HTTP calls.

Important files in the source repo:

```text
https://github.com/abhishek43501/orikaserver_proto
OrikaServer/server/Server.cpp
OrikaServer/StaticClass.cpp
OrikaServer/Manager.cpp
OrikaServer/ProtoMessageConverter.cpp
```

Observed server behavior from C++ source:

- `Server.cpp` handles `FETCH_CLIENT_POSITIONS`, `FETCH_ORDER_DATA`, and `FETCH_DEALING_DATA` after login validation.
- For `FETCH_CLIENT_POSITIONS`, it sets flags like `m_ClientWiseNetPositionStart_FirstTime`, `m_refreshClientPosition`, and later keeps `m_ClientWiseNetPositionStart` active.
- `StaticClass.cpp` sends the first position snapshot with `CLIENT_POSITION.insert` and later sends `CLIENT_POSITION.update` using `updatekey: ["login", "symbol"]`.
- `StaticClass.cpp` sends order inserts, updates, and deletes as `ORDER_DATA` with `updatekey/deletekey: ["order"]`.
- `StaticClass.cpp` maps `FETCH_DEALING_DATA` to response `DEALING_DATA`.
- `StaticClass.cpp` maps response types to protobuf fields: `CLIENT_POSITION -> clientposition`, `ORDER_DATA -> orderdata`, `DEALING_DATA -> dealingdata`.

The plugin follows those server-side semantics exactly: one reader loop stays connected, applies inserts/updates/deletes to memory, and exposes the current state.

## LLM rules to avoid errors

1. Do not create a new WebSocket connection for every question.
2. Start `orika_stream_start` once and keep it running.
3. Use `orika_stream_status` to find the active `state.json` path.
4. Use `orika_stream_query` to answer current-data questions.
5. Use `events.jsonl` only for event history/audit/trigger engines.
6. Use `state.json` or query tool for latest current values.
7. For positions, always subscribe columns before fetch. The plugin does this automatically.
8. Do not hardcode credentials. Read `.env` only.
9. Do not commit `.env`, state, logs, JSONL, or CSVs.
10. If disconnected, restart the stream; on reconnect subscriptions must be sent again.
