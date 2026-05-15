"""Smoke tests — STEP-16: student handout export."""
import inspect, sys

# ── env bootstrap ─────────────────────────────────────────────────────────────
import os
os.environ.setdefault("DATABASE_URL",  "postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya")
os.environ.setdefault("REDIS_URL",     "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",    "1889a2bea7f4c026f5b6922687e67b4a72c47780076bf12c0233b8e1f9624cca")
os.environ.setdefault("GEMINI_API_KEY","AIzaSyCxDoyH0istyuUdMb2pWN6x4huIUq7sTpQ")
os.environ.setdefault("S3_ENDPOINT",   "http://localhost:9000")
os.environ.setdefault("S3_BUCKET",     "vidya-assets")
os.environ.setdefault("ENVIRONMENT",   "development")

passed = 0

def check(n, cond, msg):
    global passed
    if not cond:
        print(f"FAIL {n} — {msg}")
        sys.exit(1)
    print(f"PASS {n} — {msg}")
    passed += 1

# 1 — schema description includes 'handout'
from app.modules.m03_course_kit.schemas import KitExportRequest
desc = KitExportRequest.model_fields["format"].description or ""
check(1, "handout" in desc, "KitExportRequest.format description includes 'handout'")

# 2 — service format guard includes 'handout'
from app.modules.m03_course_kit.service import CourseKitService
src_svc = inspect.getsource(CourseKitService.dispatch_kit_export)
check(2, "handout" in src_svc, "service dispatch_kit_export format guard includes handout")

# 3 — _generate_handout_pdf is importable
from app.workers.heavy.course_kit_export import _generate_handout_pdf
check(3, callable(_generate_handout_pdf), "_generate_handout_pdf importable and callable")

# 4 — _run_export has handout routing branch
from app.workers.heavy import course_kit_export as ce_mod
src_run = inspect.getsource(ce_mod._run_export)
check(4, "handout" in src_run, "_run_export contains handout routing branch")

# 5 — filename gets _handout suffix
check(5, "_handout" in src_run, "_run_export builds _handout filename suffix")

# 6 — handout generator never accesses faculty-sensitive attributes (AST attribute check)
import ast as _ast
src_hf = inspect.getsource(_generate_handout_pdf)
tree_hf = _ast.parse(src_hf)
accessed_attrs = {n.attr for n in _ast.walk(tree_hf) if isinstance(n, _ast.Attribute)}
forbidden_attrs = {"speaker_notes", "answer_key", "model_answer", "rubric"}
leaks = forbidden_attrs & accessed_attrs
check(6, not leaks, f"_generate_handout_pdf AST has no attribute accesses for: {forbidden_attrs} (leaks={leaks})")

# 7 — watermark text label present
check(7, "STUDENT HANDOUT" in src_hf, "watermark 'STUDENT HANDOUT' label present")

# 8 — watermark callbacks wired to doc.build
check(8,
    "onFirstPage=_draw_watermark" in src_hf and "onLaterPages=_draw_watermark" in src_hf,
    "watermark callbacks wired to doc.build(onFirstPage, onLaterPages)")

# 9 — prefixed style names avoid collision with _generate_pdf
check(9, "ho_small" in src_hf and "ho_h1" in src_hf,
      "prefixed style names 'ho_*' used (no collision with _generate_pdf)")

# 10 — SHORT_ANSWER blank lines present
check(10, "SHORT_ANSWER" in src_hf,
      "SHORT_ANSWER branch writes blank answer lines in handout")

print(f"\n{passed}/10 STEP-16 smoke assertions passed.")
