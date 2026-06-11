#!/usr/bin/env python
"""Query Orika live-memory state written by orika_live_cli.py.

This does not connect to Orika. It reads state.json maintained by the long-running
stream process and returns current in-memory data.

Examples:
  python app/orika_query_state.py --state-file orika_live_output/state.json --stream orders --limit 5
  python app/orika_query_state.py --state-file orika_live_output/state.json --stream positions --key LOGIN:SYMBOL
  python app/orika_query_state.py --state-file orika_live_output/state.json --stream deals --field symbol --equals XAUUSD
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_state(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise SystemExit(json.dumps({"success": False, "error": f"state file not found: {p}"}))
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Query Orika live-memory state.json")
    parser.add_argument("--state-file", default="orika_live_output/state.json")
    parser.add_argument("--stream", choices=["orders", "deals", "positions", "summary"], default="summary")
    parser.add_argument("--key", help="Exact in-memory row key/id. Orders use order id; deals use id; positions use login:symbol.")
    parser.add_argument("--field", help="Filter rows where this field equals --equals, or return this field for --key.")
    parser.add_argument("--equals", help="Filter value used with --field.")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    state = load_state(args.state_file)
    if args.stream == "summary":
        out = {k: state.get(k) for k in ["success", "status", "updated_at", "last_event", "counts", "totals", "streams", "source"]}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    table = state.get("data", {}).get(args.stream, {})
    if not isinstance(table, dict):
        table = {}

    if args.key:
        row = table.get(args.key)
        if row is None:
            print(json.dumps({"success": False, "stream": args.stream, "key": args.key, "error": "not found"}, ensure_ascii=False))
            return 1
        if args.field:
            print(json.dumps({"success": True, "stream": args.stream, "key": args.key, "field": args.field, "value": row.get(args.field)}, ensure_ascii=False))
        else:
            print(json.dumps({"success": True, "stream": args.stream, "key": args.key, "row": row}, ensure_ascii=False, indent=2))
        return 0

    rows = list(table.values())
    if args.field and args.equals is not None:
        rows = [r for r in rows if str(r.get(args.field, "")) == str(args.equals)]

    print(json.dumps({
        "success": True,
        "stream": args.stream,
        "total": len(table),
        "returned": min(len(rows), args.limit),
        "rows": rows[: args.limit],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
