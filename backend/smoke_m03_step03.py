"""STEP-03 smoke tests — M03 Pydantic schemas."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",    "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",   "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.modules.m03_course_kit.schemas import (
    # embedded sub-models
    SlideContent, QuizletOption, RubricCriterion,
    TeachingPlanWeek, LessonPlanSession, ResourceItem,
    # KitSlide
    KitSlideCreate, KitSlideUpdate, KitSlideResponse, KitSlideReorder,
    # KitQuizlet
    KitQuizletCreate, KitQuizletUpdate, KitQuizletResponse,
    # KitAssignment
    KitAssignmentCreate, KitAssignmentUpdate, KitAssignmentResponse,
    # CourseKit
    CourseKitCreate, CourseKitUpdate, CourseKitResponse,
    CourseKitDetail, CourseKitListResponse,
    CourseKitStatusResponse, CourseKitVersionResponse,
    # actions
    GenerateKitRequest, KitAIJobResponse,
    PublishRequest, ArchiveRequest, ForkRequest,
    # compliance
    ComplianceViolation, ComplianceCheckResponse,
    # export
    KitExportRequest, KitExportJobResponse,
)
import uuid

# ---------------------------------------------------------------------------
# 1. Embedded sub-model round-trips
# ---------------------------------------------------------------------------
sc = SlideContent(bullets=["Point A", "Point B"], key_concepts=["ML"], image_hint="diagram")
assert sc.bullets == ["Point A", "Point B"]
assert sc.image_hint == "diagram"

opt = QuizletOption(label="A", text="First option")
assert opt.label == "A"

rc = RubricCriterion(criterion="Clarity", description="Is the answer clear?", max_marks=5)
assert rc.max_marks == 5

tpw = TeachingPlanWeek(week=1, topic="Introduction", hours=3, activities=["Lecture"])
assert tpw.co_references == []

lps = LessonPlanSession(session=1, week=1, topic="ML Basics", main_content="Intro to ML")
assert lps.duration_minutes == 60

ri = ResourceItem(title="ML Textbook", resource_type="book_chapter")
assert ri.url is None

# ---------------------------------------------------------------------------
# 2. KitSlide — create with required fields, update optional
# ---------------------------------------------------------------------------
sid = uuid.uuid4()
kid = uuid.uuid4()

slide_create = KitSlideCreate(slide_number=1, title="Introduction to ML")
assert slide_create.speaker_notes is None
assert slide_create.bloom_level is None

slide_update = KitSlideUpdate(title="Updated Title")
assert slide_update.content is None

# from_attributes response
slide_resp = KitSlideResponse.model_validate({
    "id": sid, "kit_id": kid, "slide_number": 1, "title": "Intro",
    "content": {"bullets": [], "key_concepts": []},
    "speaker_notes": "Explain slowly",
    "bloom_level": "UNDERSTAND",
    "co_reference": "CO1",
    "created_at": "2026-05-12T10:00:00Z",
    "updated_at": None,
})
assert slide_resp.speaker_notes == "Explain slowly"
# router should null this for DEAN — schema allows None
slide_resp_dean = slide_resp.model_copy(update={"speaker_notes": None})
assert slide_resp_dean.speaker_notes is None

# ---------------------------------------------------------------------------
# 3. KitQuizlet — answer_key present in Response but nullable
# ---------------------------------------------------------------------------
qid = uuid.uuid4()

quiz_create = KitQuizletCreate(
    question_number=1,
    question_text="What is supervised learning?",
    question_type="MCQ",
    options=[{"label": "A", "text": "Option A"}, {"label": "B", "text": "Option B"}],
    answer_key={"correct_option": "A"},
    answer_explanation="Supervised learning uses labelled data.",
    bloom_level="UNDERSTAND",
    co_reference="CO2",
)
assert quiz_create.answer_key == {"correct_option": "A"}

quiz_resp = KitQuizletResponse.model_validate({
    "id": qid, "kit_id": kid, "question_number": 1,
    "question_text": "What is supervised learning?",
    "question_type": "MCQ",
    "options": [{"label": "A", "text": "Option A"}],
    "answer_key": {"correct_option": "A"},
    "answer_explanation": "Uses labelled data.",
    "bloom_level": "UNDERSTAND",
    "co_reference": "CO2",
    "created_at": "2026-05-12T10:00:00Z",
    "updated_at": None,
})
assert quiz_resp.answer_key == {"correct_option": "A"}
# DEAN redaction — router sets to None
quiz_dean = quiz_resp.model_copy(update={"answer_key": None})
assert quiz_dean.answer_key is None

# ---------------------------------------------------------------------------
# 4. KitAssignment — model_answer present in Response but nullable
# ---------------------------------------------------------------------------
aid = uuid.uuid4()

assign_create = KitAssignmentCreate(
    assignment_number=1,
    title="Implement Logistic Regression",
    assignment_type="HOMEWORK",
    question_text="Implement and evaluate a logistic regression classifier.",
    complexity_level="UG",
    model_answer="Train using sklearn, evaluate with accuracy_score.",
    rubric=[{"criterion": "Correctness", "description": "Output matches expected", "max_marks": 10}],
    bloom_level="APPLY",
    co_reference="CO3",
)
assert assign_create.current_events_toggle is False
assert len(assign_create.rubric) == 1

assign_resp = KitAssignmentResponse.model_validate({
    "id": aid, "kit_id": kid, "assignment_number": 1,
    "title": "Implement LR", "assignment_type": "HOMEWORK",
    "question_text": "Build a classifier.", "complexity_level": "UG",
    "current_events_toggle": False,
    "model_answer": "Use sklearn.",
    "rubric": [{"criterion": "Correctness", "description": "Correct output", "max_marks": 10}],
    "bloom_level": "APPLY", "co_reference": "CO3",
    "created_at": "2026-05-12T10:00:00Z", "updated_at": None,
})
assert assign_resp.model_answer == "Use sklearn."
# DEAN redaction
assign_dean = assign_resp.model_copy(update={"model_answer": None})
assert assign_dean.model_answer is None

# ---------------------------------------------------------------------------
# 5. CourseKit create / response / detail
# ---------------------------------------------------------------------------
syll_id = uuid.uuid4()

kit_create = CourseKitCreate(syllabus_id=syll_id, unit_number=1)
assert kit_create.complexity_level.value == "UG"
assert kit_create.tone is None

kit_update = CourseKitUpdate(tone="conversational")
assert kit_update.complexity_level is None

kit_resp = CourseKitResponse.model_validate({
    "id": kid, "syllabus_id": syll_id, "unit_number": 1, "version": 1,
    "parent_version_id": None, "status": "DRAFT",
    "complexity_level": "UG", "tone": None, "custom_instructions": None,
    "ai_model": None, "created_by_user_id": uuid.uuid4(),
    "published_by_user_id": None, "published_at": None,
    "created_at": "2026-05-12T10:00:00Z", "updated_at": None,
})
assert kit_resp.status.value == "DRAFT"

# CourseKitDetail extends CourseKitResponse with JSONB + children
kit_detail = CourseKitDetail.model_validate({
    **kit_resp.model_dump(),
    "teaching_plan": [{"week": 1, "topic": "Intro", "hours": 3}],
    "lesson_plans":  [{"session": 1, "week": 1, "topic": "Intro", "duration_minutes": 60}],
    "resources":     [{"title": "Textbook", "resource_type": "book_chapter"}],
    "slides": [], "quizlets": [], "assignments": [],
})
assert len(kit_detail.teaching_plan) == 1
assert kit_detail.slides == []

# List response
kit_list = CourseKitListResponse(total=2, page=1, page_size=20, items=[kit_resp])
assert kit_list.total == 2

# Status response (state-transition return)
kit_status = CourseKitStatusResponse.model_validate({
    "id": kid, "version": 1, "status": "PUBLISHED", "updated_at": None,
})
assert kit_status.status.value == "PUBLISHED"

# Version response
kit_version = CourseKitVersionResponse.model_validate({
    "id": kid, "version": 2, "parent_version_id": None,
    "status": "ARCHIVED", "created_by_user_id": uuid.uuid4(),
    "published_at": None, "created_at": "2026-05-12T10:00:00Z",
})
assert kit_version.status.value == "ARCHIVED"

# ---------------------------------------------------------------------------
# 6. Action schemas
# ---------------------------------------------------------------------------
gen_req = GenerateKitRequest(custom_instructions="Focus on practical examples", tone="formal")
assert gen_req.complexity_level is None

job_resp = KitAIJobResponse(job_id=uuid.uuid4(), kit_id=kid)
assert job_resp.status == "queued"

pub_req = PublishRequest()
assert pub_req.comment is None

arc_req = ArchiveRequest(reason="Replaced by v2")
assert arc_req.reason == "Replaced by v2"

fork_req = ForkRequest(change_note="Updating for new semester")
assert fork_req.change_note == "Updating for new semester"

# ---------------------------------------------------------------------------
# 7. Compliance schemas
# ---------------------------------------------------------------------------
violation = ComplianceViolation(code="SLIDE_MIN_NOT_MET", message="Need ≥8 slides", severity="ERROR")
assert violation.severity == "ERROR"

compliance = ComplianceCheckResponse(passed=False, violations=[violation])
assert not compliance.passed

# ---------------------------------------------------------------------------
# 8. Export schemas
# ---------------------------------------------------------------------------
export_req = KitExportRequest(format="pptx")
assert export_req.format == "pptx"

export_resp = KitExportJobResponse(job_id=uuid.uuid4(), kit_id=kid, format="pptx")
assert export_resp.status == "queued"

# ---------------------------------------------------------------------------
# 9. Enum values in schemas match model enums exactly
# ---------------------------------------------------------------------------
from app.modules.m03_course_kit.models import (
    CourseKitStatus, ComplexityLevel, QuizletType, AssignmentType, BloomLevel,
)
assert kit_resp.status    == CourseKitStatus.DRAFT
assert kit_status.status  == CourseKitStatus.PUBLISHED
assert quiz_create.question_type == QuizletType.MCQ
assert assign_create.assignment_type == AssignmentType.HOMEWORK
assert assign_create.bloom_level     == BloomLevel.APPLY

# ---------------------------------------------------------------------------
# 10. All 28 schema classes are importable (count check)
# ---------------------------------------------------------------------------
schema_classes = [
    SlideContent, QuizletOption, RubricCriterion,
    TeachingPlanWeek, LessonPlanSession, ResourceItem,
    KitSlideCreate, KitSlideUpdate, KitSlideResponse, KitSlideReorder,
    KitQuizletCreate, KitQuizletUpdate, KitQuizletResponse,
    KitAssignmentCreate, KitAssignmentUpdate, KitAssignmentResponse,
    CourseKitCreate, CourseKitUpdate, CourseKitResponse,
    CourseKitDetail, CourseKitListResponse,
    CourseKitStatusResponse, CourseKitVersionResponse,
    GenerateKitRequest, KitAIJobResponse,
    PublishRequest, ArchiveRequest, ForkRequest,
    ComplianceViolation, ComplianceCheckResponse,
    KitExportRequest, KitExportJobResponse,
]
assert len(schema_classes) == 32, f"Expected 32 schema classes, got {len(schema_classes)}"

print("STEP-03: all 10 assertions passed.")
