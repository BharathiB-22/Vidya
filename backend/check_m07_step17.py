"""STEP-17 smoke test — Celery worker includes all M07 tasks."""
from app.workers.celery_app import celery_app

include = celery_app.conf.include
m07_tasks = [
    "app.workers.heavy.evaluate_research_proposal",
    "app.workers.heavy.evaluate_research_document",
    "app.workers.heavy.process_viva_session",
]
for t in m07_tasks:
    assert t in include, f"Missing from celery include: {t}"

# Verify tasks are all loadable
from app.workers.heavy.evaluate_research_proposal import evaluate_research_proposal
from app.workers.heavy.evaluate_research_document import evaluate_research_document
from app.workers.heavy.process_viva_session import process_viva_session

assert evaluate_research_proposal.name == "app.workers.heavy.evaluate_research_proposal"
assert evaluate_research_document.name == "app.workers.heavy.evaluate_research_document"
assert process_viva_session.name == "app.workers.heavy.process_viva_session"

# Routing: all should go to celery-heavy queue
routing = celery_app.conf.task_routes
route_pattern = list(routing.keys())[0]
assert "heavy" in route_pattern
assert routing[route_pattern]["queue"] == "celery-heavy"

print("STEP-17 smoke: Celery worker registration PASS")
