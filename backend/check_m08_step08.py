"""STEP-08..09 smoke test — audit events + router structure."""

# ---- STEP-08: Audit events ----
from app.core.audit_log.models import AuditEventType

# All 12 new M08 audit event types
assert AuditEventType.EXAM_PAPER_CREATED              == "EXAM_PAPER_CREATED"
assert AuditEventType.EXAM_PAPER_GENERATION_QUEUED    == "EXAM_PAPER_GENERATION_QUEUED"
assert AuditEventType.EXAM_PAPER_GENERATION_COMPLETED == "EXAM_PAPER_GENERATION_COMPLETED"
assert AuditEventType.EXAM_PAPER_GENERATION_FAILED    == "EXAM_PAPER_GENERATION_FAILED"
assert AuditEventType.EXAM_PAPER_QUESTION_EDITED      == "EXAM_PAPER_QUESTION_EDITED"
assert AuditEventType.EXAM_PAPER_QUESTION_REPLACED    == "EXAM_PAPER_QUESTION_REPLACED"
assert AuditEventType.EXAM_PAPER_SUBMITTED            == "EXAM_PAPER_SUBMITTED"       # Gate 1
assert AuditEventType.EXAM_PAPER_BOARD_APPROVED       == "EXAM_PAPER_BOARD_APPROVED"  # Gate 2
assert AuditEventType.EXAM_PAPER_BOARD_RETURNED       == "EXAM_PAPER_BOARD_RETURNED"
assert AuditEventType.EXAM_PAPER_SEALED               == "EXAM_PAPER_SEALED"          # Gate 3
assert AuditEventType.EXAM_PAPER_RELEASED             == "EXAM_PAPER_RELEASED"
assert AuditEventType.EXAM_PAPER_EXPORTED             == "EXAM_PAPER_EXPORTED"

# M07 events still present (regression check)
assert AuditEventType.VIVA_GUIDE_RATIFIED     == "VIVA_GUIDE_RATIFIED"
assert AuditEventType.RESEARCH_PROBLEM_SUBMITTED == "RESEARCH_PROBLEM_SUBMITTED"

# M06 events still present
assert AuditEventType.LAB_SUBMISSION_RATIFIED  == "LAB_SUBMISSION_RATIFIED"

print("STEP-08 (audit events): 12 M08 events + regression OK")

# ---- STEP-09: Router structure ----
from app.modules.m08_exam_setter.router import router

# Router has routes
routes = {r.path for r in router.routes}
assert "" in routes or any("" in r for r in routes) or len(router.routes) > 0

# Spot-check key route paths
paths = [r.path for r in router.routes]
assert any("submit" in p for p in paths),         "submit endpoint missing"
assert any("board-decision" in p for p in paths), "board-decision endpoint missing"
assert any("seal" in p for p in paths),           "seal endpoint missing"
assert any("blooms" in p for p in paths),         "blooms endpoint missing"
assert any("export" in p for p in paths),         "export endpoint missing"
assert any("jobs" in p for p in paths),           "jobs polling endpoint missing"
assert any("board" in p and "pending" in p for p in paths), "board/pending endpoint missing"

# Count routes (expecting 14+)
print(f"Router routes: {len(router.routes)} routes defined")
assert len(router.routes) >= 12, f"Expected >= 12 routes, got {len(router.routes)}"

print("STEP-09 (router): all key endpoints present. OK")
print("All STEP-08..09 assertions passed.")
