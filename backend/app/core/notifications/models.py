import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class NotificationType(str, enum.Enum):
    TASK_COMPLETE       = "TASK_COMPLETE"
    TASK_FAILED         = "TASK_FAILED"
    SUBMISSION_FLAGGED  = "SUBMISSION_FLAGGED"
    REVIEW_REQUESTED    = "REVIEW_REQUESTED"
    OUTCOME_PUBLISHED   = "OUTCOME_PUBLISHED"
    GENERAL             = "GENERAL"

    # SIS — H52
    ENROLLMENT_CREATED          = "ENROLLMENT_CREATED"
    ENROLLMENT_MOVED            = "ENROLLMENT_MOVED"
    ENROLLMENT_UNENROLLED       = "ENROLLMENT_UNENROLLED"
    USN_ASSIGNED                = "USN_ASSIGNED"
    ADMISSION_YEAR_ASSIGNED     = "ADMISSION_YEAR_ASSIGNED"
    COURSE_ASSIGNED             = "COURSE_ASSIGNED"
    COURSE_ASSIGNMENT_REVOKED   = "COURSE_ASSIGNMENT_REVOKED"

    # SIS Attendance — H55
    ATTENDANCE_SHORTAGE_WARNING = "ATTENDANCE_SHORTAGE_WARNING"

    # SIS Internal Marks — H57
    INTERNAL_MARKS_PUBLISHED = "INTERNAL_MARKS_PUBLISHED"

    # Syllabus lifecycle — M02
    #
    # SYLLABUS_REJECTED / _REVISION_REQUESTED / _SUBMITTED belonged to the
    # faculty-authors-syllabus workflow that Phase A removed. Nothing emits them
    # any more; they are kept only so historical notification rows still
    # deserialize. Do not add new emitters.
    SYLLABUS_REJECTED           = "SYLLABUS_REJECTED"            # retired
    SYLLABUS_REVISION_REQUESTED = "SYLLABUS_REVISION_REQUESTED"  # retired
    SYLLABUS_SUBMITTED          = "SYLLABUS_SUBMITTED"           # retired
    SYLLABUS_APPROVED           = "SYLLABUS_APPROVED"
    SYLLABUS_VERSION_CREATED    = "SYLLABUS_VERSION_CREATED"

    # Curriculum governance — Phase A. Two messages, one each way.
    #
    # SUBMITTED  Dean -> the Board ("there is a curriculum waiting for you") and
    #            back to the Dean ("it has entered review; it is read-only now").
    # FINALIZED  the Board -> the Dean, the one message that crosses back:
    #            "your curriculum is finalized, here is what changed, publish it."
    CURRICULUM_SUBMITTED        = "CURRICULUM_SUBMITTED"
    CURRICULUM_FINALIZED        = "CURRICULUM_FINALIZED"

    # The Dean's half of the workflow. Two more messages, and they are his.
    #
    # READY_TO_PUBLISH  the last of his execution documents has been approved — the
    #                   curriculum can now be released. Nothing else is waiting on him,
    #                   and nothing publishes itself.
    #
    # The message telling him that the Board has finished, and that his internship and
    # project documents can now be prepared, is CURRICULUM_FINALIZED — it already
    # crosses back to him at exactly that moment, and a second notification saying the
    # same thing in different words is how people learn to ignore notifications.
    CURRICULUM_READY_TO_PUBLISH = "CURRICULUM_READY_TO_PUBLISH"

    # Academic ownership — Phase 1 Wave 1
    PROGRAM_ASSIGNED            = "PROGRAM_ASSIGNED"
    PROGRAM_ASSIGNMENT_REVOKED  = "PROGRAM_ASSIGNMENT_REVOKED"

    # Course Kit lifecycle — M03.
    # NOTE: types reserved for the Course-Kit dean-review workflow (roadmap
    # Wave 3). No emitter fires these yet because course-kit publish is a
    # single-actor action today — see docs/enterprise-ux-erp-governance-audit.md.
    COURSE_KIT_SUBMITTED        = "COURSE_KIT_SUBMITTED"
    COURSE_KIT_APPROVED         = "COURSE_KIT_APPROVED"
    COURSE_KIT_REJECTED         = "COURSE_KIT_REJECTED"

    # Assignments — M04 (theory/coursework assignments, separate from M06 Labs)
    ASSIGNMENT_PUBLISHED         = "ASSIGNMENT_PUBLISHED"
    ASSIGNMENT_GRADED            = "ASSIGNMENT_GRADED"
    ASSIGNMENT_RETURNED          = "ASSIGNMENT_RETURNED"
    ASSIGNMENT_EVALUATOR_ASSIGNED   = "ASSIGNMENT_EVALUATOR_ASSIGNED"    # -> evaluator, at publish
    ASSIGNMENT_SUBMISSION_RECEIVED  = "ASSIGNMENT_SUBMISSION_RECEIVED"   # -> faculty, on student submit
    ASSIGNMENT_EVALUATION_COMPLETED = "ASSIGNMENT_EVALUATION_COMPLETED"  # -> faculty, when all graded
    ASSIGNMENT_RESULTS_RELEASED     = "ASSIGNMENT_RESULTS_RELEASED"      # -> students, on release

    # Labs & Assignment Evaluator — M06 (wired up in Phase 3; previously silent)
    LAB_PUBLISHED               = "LAB_PUBLISHED"
    LAB_GRADED                  = "LAB_GRADED"

    # Research Supervision — M07.
    #
    # One message at each end of the three human gates the module already has:
    # the guide is told when something is waiting for their decision, and the
    # student is told once that decision is made. The AI never decides — it only
    # produces the advisory the guide reads, so the _EVALUATED pair goes to the
    # guide, never to the student.
    VIVA_SCHEDULED                = "VIVA_SCHEDULED"                # -> student
    VIVA_RATIFIED                 = "VIVA_RATIFIED"                 # -> student
    RESEARCH_PROPOSAL_SUBMITTED   = "RESEARCH_PROPOSAL_SUBMITTED"   # -> guide
    RESEARCH_PROPOSAL_EVALUATED   = "RESEARCH_PROPOSAL_EVALUATED"   # -> guide
    RESEARCH_PROPOSAL_DECIDED     = "RESEARCH_PROPOSAL_DECIDED"     # -> student
    RESEARCH_DOCUMENT_EVALUATED   = "RESEARCH_DOCUMENT_EVALUATED"   # -> guide
    RESEARCH_DOCUMENT_REVIEWED    = "RESEARCH_DOCUMENT_REVIEWED"    # -> student
    # An AI stage could not run at all (e.g. ASR unavailable). Sent to the guide
    # so a missing advisory is visible rather than silent — the human gate still
    # holds, and they can proceed manually.
    RESEARCH_EVALUATION_FAILED    = "RESEARCH_EVALUATION_FAILED"    # -> guide


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index("ix_notifications_recipient_is_read", "recipient_user_id", "is_read"),
    )

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_user_id = Column(UUID(as_uuid=True), nullable=False)
    notification_type = Column(
        String,
        nullable=False,
    )
    title             = Column(String,  nullable=False)
    body              = Column(Text,    nullable=False)
    entity_type       = Column(String,  nullable=True)   # e.g. "TaskJob", "Submission"
    entity_id         = Column(String,  nullable=True)   # str of entity PK
    is_read           = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at        = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    read_at           = Column(DateTime(timezone=True), nullable=True)
