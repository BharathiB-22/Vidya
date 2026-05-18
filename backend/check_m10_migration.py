"""Verify M10 migration file revision chain."""
import importlib.util, pathlib

path = pathlib.Path("alembic/tenant_versions/0013_tenant_create_m10_bell_curve.py")
spec = importlib.util.spec_from_file_location("mig0013", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

assert m.revision      == "0013ten", f"expected 0013ten, got {m.revision}"
assert m.down_revision == "0012ten", f"expected 0012ten, got {m.down_revision}"
print(f"revision:      {m.revision}")
print(f"down_revision: {m.down_revision}")
print("Migration chain OK")
