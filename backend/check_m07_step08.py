"""STEP-08 smoke test — router imports and endpoint count."""
from app.modules.m07_research_supervision.router import router

routes = [r for r in router.routes]
print(f"  Router has {len(routes)} routes")

assert len(routes) >= 20, f"Expected >=20 routes, got {len(routes)}"

paths = {r.path for r in routes}
gate_endpoints = [
    "/problems/{problem_id}/decide",
    "/documents/{doc_id}/review",
    "/vivas/{viva_id}/ratify",
]
for ep in gate_endpoints:
    assert ep in paths, f"Missing human-gate route: {ep}"

print("STEP-08 smoke: router PASS")
