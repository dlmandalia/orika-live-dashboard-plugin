from pathlib import Path
import py_compile
root = Path(__file__).resolve().parents[1]
for rel in ["__init__.py", "schemas.py", "tools.py", "app/orika_live_cli.py", "app/live_orders_server.py"]:
    py_compile.compile(str(root / rel), doraise=True)
for rel in ["plugin.yaml", "app/orika_live_cli.py", "app/generated/clientmessage_pb2.py"]:
    assert (root / rel).exists(), rel
manifest = (root / "plugin.yaml").read_text(encoding="utf-8")
assert "orika_stream_start" in manifest
assert "orika_dashboard_start" not in manifest
print("smoke ok")
