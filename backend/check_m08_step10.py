"""STEP-10..11 smoke test — Celery tasks + celery_app include + main.py router."""
import importlib.util, pathlib

# ---- Celery task imports ----
from app.workers.heavy.generate_exam_paper import generate_exam_paper
from app.workers.heavy.release_exam_paper  import release_exam_paper

assert generate_exam_paper.name == "app.workers.heavy.generate_exam_paper", \
    f"Wrong task name: {generate_exam_paper.name}"
assert release_exam_paper.name == "app.workers.heavy.release_exam_paper", \
    f"Wrong task name: {release_exam_paper.name}"

print("Celery tasks: names OK")

# ---- celery_app include list ----
from app.workers.celery_app import celery_app

includes = celery_app.conf.include
assert "app.workers.heavy.generate_exam_paper" in includes, "generate_exam_paper missing from include"
assert "app.workers.heavy.release_exam_paper"  in includes, "release_exam_paper missing from include"

# Regression: existing tasks still in include
assert "app.workers.heavy.evaluate_lab_submission"    in includes
assert "app.workers.heavy.evaluate_research_proposal" in includes
assert "app.workers.heavy.process_viva_session"       in includes

print(f"celery_app.include: {len(includes)} tasks registered. OK")

# ---- main.py router include ----
main_path = pathlib.Path("app/main.py")
content   = main_path.read_text(encoding="utf-8")
assert "exam_router" in content,          "exam_router import missing from main.py"
assert 'prefix="/exams"' in content,     'prefix="/exams" missing from main.py'
assert 'prefix="/research"' in content,  "research router still present (regression check)"

print("main.py: exam_router registered at /exams. OK")
print("All STEP-10..11 assertions passed.")
