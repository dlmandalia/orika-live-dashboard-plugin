# Orika Live Data Plugin Installed

Start the CLI live stream from Hermes by asking:

```text
Start the Orika live stream using .env and write all data to orika_live_output
```

The stream connects to Orika, stays live, keeps data in memory, and writes:

```text
orika_live_output/events.jsonl
orika_live_output/state.json
orika_live_output/orders_snapshot.csv
orika_live_output/deals_snapshot.csv
orika_live_output/positions_snapshot.csv
```

Use `orika_stream_query` to query live memory from `state.json` without reconnecting.

Credentials must be in your local `.env`. They are not saved by the plugin.

For LLM/CLI guidance, read:

```text
docs/LIVE_MEMORY_EVENT_SYSTEM.md
```
