"""
STEP-18 smoke: Celery task wiring + final checks.
"""
import os, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "1889a2bea7f4c026f5b6922687e67b4a72c47780076bf12c0233b8e1f9624cca")
os.environ.setdefault("ENVIRONMENT", "development")

from app.workers.heavy.generate_exam_paper import generate_exam_paper
from app.workers.heavy.release_exam_paper import release_exam_paper
from app.workers.celery_app import celery_app

assert callable(generate_exam_paper)
assert generate_exam_paper.name == "app.workers.heavy.generate_exam_paper"
assert callable(release_exam_paper)
assert release_exam_paper.name == "app.workers.heavy.release_exam_paper"

inc = celery_app.conf.include
assert "app.workers.heavy.generate_exam_paper" in inc
assert "app.workers.heavy.release_exam_paper" in inc
# M06/M07 not regressed
assert "app.workers.heavy.evaluate_lab_submission" in inc
assert "app.workers.heavy.evaluate_research_proposal" in inc
assert "app.workers.heavy.process_viva_session" in inc

# Router reachable from main app
from app.main import app as fastapi_app
paths = [r.path for r in fastapi_app.routes]
exam_paths = [p for p in paths if "/exams" in p]
assert len(exam_paths) >= 5, f"Expected ≥5 exam routes, got {len(exam_paths)}"

print("STEP-18 smoke: PASSED")
print(f"  generate_exam_paper  -> {generate_exam_paper.name}")
print(f"  release_exam_paper   -> {release_exam_paper.name}")
print(f"  Celery include count: {len(inc)}")
print(f"  Exam router paths:    {len(exam_paths)}")
