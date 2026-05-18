"""STEP-10 smoke test — Celery tasks importable + main.py has M07 router."""

# 1. Celery tasks import without errors
from app.workers.heavy.evaluate_research_proposal import evaluate_research_proposal
from app.workers.heavy.evaluate_research_document import evaluate_research_document
from app.workers.heavy.process_viva_session import process_viva_session

assert callable(evaluate_research_proposal)
assert callable(evaluate_research_document)
assert callable(process_viva_session)

# 2. Task names match routing pattern
for task, expected_name in [
    (evaluate_research_proposal, "app.workers.heavy.evaluate_research_proposal"),
    (evaluate_research_document, "app.workers.heavy.evaluate_research_document"),
    (process_viva_session,       "app.workers.heavy.process_viva_session"),
]:
    assert task.name == expected_name, f"Bad task name: {task.name}"

# 3. main.py imports M07 router
from app.main import app
routes = [r.path for r in app.routes]
m07_routes = [p for p in routes if "/research/" in p or p.startswith("/research")]
assert len(m07_routes) >= 5, f"Expected >=5 /research/* routes in main, got: {m07_routes}"

print(f"STEP-10 smoke: Celery tasks + main.py registration PASS ({len(m07_routes)} /research routes)")
