from pathlib import Path
import py_compile
root = Path(__file__).resolve().parents[1]
for rel in ["__init__.py", "schemas.py", "tools.py", "app/live_orders_server.py"]:
    py_compile.compile(str(root / rel), doraise=True)
for rel in ["plugin.yaml", "app/live_orders.html", "app/live_deals.html", "app/generated/clientmessage_pb2.py"]:
    assert (root / rel).exists(), rel
print("smoke ok")
