"""STEP-09 smoke test — M07 audit event types."""
from app.core.audit_log.models import AuditEventType

required = [
    "RESEARCH_PROBLEM_SUBMITTED",
    "RESEARCH_PROBLEM_EVAL_QUEUED",
    "RESEARCH_PROBLEM_AI_EVALUATED",
    "RESEARCH_PROBLEM_GUIDE_DECIDED",
    "RESEARCH_PROBLEM_AI_GENERATED",
    "RESEARCH_DOCUMENT_SUBMITTED",
    "RESEARCH_DOCUMENT_EVAL_QUEUED",
    "RESEARCH_DOCUMENT_AI_EVALUATED",
    "RESEARCH_DOCUMENT_GUIDE_REVIEWED",
    "VIVA_SESSION_SCHEDULED",
    "VIVA_SESSION_STARTED",
    "VIVA_SESSION_COMPLETED",
    "VIVA_AI_EVALUATED",
    "VIVA_GUIDE_RATIFIED",
]

for name in required:
    assert hasattr(AuditEventType, name), f"Missing: {name}"
    assert getattr(AuditEventType, name).value == name

# Regression: previous M06 events still exist
for name in ["LAB_REPORT_REQUESTED", "LAB_REPORT_COMPLETED",
             "LAB_SUBMISSION_RATIFIED", "LAB_EVAL_COMPLETED"]:
    assert hasattr(AuditEventType, name), f"Regression — missing M06 event: {name}"

print("STEP-09 smoke: audit event types PASS")
