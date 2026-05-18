"""STEP-02..03 smoke test — M08 repository + schemas."""
# -- Repository imports --
from app.modules.m08_exam_setter.repository import (
    ExamPaperRepository,
    ExamQuestionRepository,
    BloomsRepository,
    TaskJobPublicRepository,
)

# Static method presence
assert callable(ExamPaperRepository.create)
assert callable(ExamPaperRepository.get_by_id)
assert callable(ExamPaperRepository.list_for_faculty)
assert callable(ExamPaperRepository.list_board_pending)
assert callable(ExamPaperRepository.list_all)
assert callable(ExamPaperRepository.set_generation_job)
assert callable(ExamPaperRepository.set_generation_result)
assert callable(ExamPaperRepository.set_submitted)
assert callable(ExamPaperRepository.set_board_decision)
assert callable(ExamPaperRepository.set_sealed)
assert callable(ExamPaperRepository.set_released)

assert callable(ExamQuestionRepository.bulk_create)
assert callable(ExamQuestionRepository.list_by_paper)
assert callable(ExamQuestionRepository.get_by_id)
assert callable(ExamQuestionRepository.update_question)
assert callable(ExamQuestionRepository.delete)

assert callable(BloomsRepository.upsert)
assert callable(BloomsRepository.get_by_paper)

assert callable(TaskJobPublicRepository.create)

print("Repository: all methods present. OK")

# -- Schema imports --
from app.modules.m08_exam_setter.schemas import (
    QuestionFormatConfig,
    BloomsDistribution,
    ExamPaperCreate,
    ExamPaperResponse,
    ExamPaperListResponse,
    ExamQuestionResponse,
    ExamQuestionWithAnswerResponse,
    ExamQuestionUpdate,
    BloomsComplianceResponse,
    BoardDecisionRequest,
    SealRequest,
    JobStatusResponse,
)

# QuestionFormatConfig validation
cfg = QuestionFormatConfig(mcq_count=5, short_count=3, long_count=2, problem_count=0)
assert cfg.mcq_count == 5

try:
    QuestionFormatConfig(mcq_count=0, short_count=0, long_count=0, problem_count=0)
    assert False, "Should have raised"
except Exception:
    pass  # expected

# BloomsDistribution validation
bd = BloomsDistribution(
    remember=20, understand=20, apply=20, analyse=20, evaluate=10, create=10
)
assert abs(bd.remember + bd.understand + bd.apply + bd.analyse + bd.evaluate + bd.create - 100) < 1

try:
    BloomsDistribution(remember=10, understand=10, apply=10, analyse=10, evaluate=10, create=10)
    assert False, "Should raise: sum=60"
except Exception:
    pass  # expected

# BoardDecisionRequest: return requires comment
try:
    BoardDecisionRequest(approved=False, board_comment=None)
    assert False, "Should raise: no comment on return"
except Exception:
    pass  # expected

ok_return = BoardDecisionRequest(approved=False, board_comment="Needs revision in Unit 3.")
assert ok_return.board_comment is not None

ok_approve = BoardDecisionRequest(approved=True)
assert ok_approve.approved is True

# SealRequest: past date rejected
from datetime import datetime, timezone, timedelta
past = datetime.now(timezone.utc) - timedelta(hours=1)
try:
    SealRequest(release_at=past)
    assert False, "Should raise: past release_at"
except Exception:
    pass  # expected

future = datetime.now(timezone.utc) + timedelta(days=7)
sr = SealRequest(release_at=future)
assert sr.release_at > datetime.now(timezone.utc)

# ExamQuestionWithAnswerResponse has model_answer
assert "model_answer" in ExamQuestionWithAnswerResponse.model_fields
# ExamQuestionResponse does NOT expose model_answer or correct_option
assert "model_answer"   not in ExamQuestionResponse.model_fields
assert "correct_option" not in ExamQuestionResponse.model_fields

print("Schemas: all assertions passed. OK")
print("All STEP-02..03 assertions passed.")
