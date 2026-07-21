"""
M08 Exam Setter — H-35 Productization tests (STEP-13).

Coverage areas (10):
  1. INTERNAL workflow path
  2. BOARD_EXAM workflow path
  3. Faculty approve flow
  4. Scrutinizer flow
  5. Question regeneration flow
  6. Question bank promotion on board approval
  7. Internal marks submit gate
  8. Internal marks dean lock gate
  9. CO coverage report generation
 10. Unit coverage report generation

Plus supplementary:
  11. H-35 schema validators
  12. H-35 router wiring
  13. H-35 audit events
  14. H-35 models
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ===========================================================================
# Helpers
# ===========================================================================

def _paper(
    *,
    status: str = "GENERATED",
    workflow: str = "BOARD_EXAM",
    creator_id=None,
    scrutinizer_id=None,
):
    m = MagicMock()
    m.id = uuid4()
    m.created_by = creator_id or uuid4()
    m.status = status
    m.exam_workflow = workflow
    m.scrutinizer_id = scrutinizer_id
    m.course_id = uuid4()
    return m


def _ims(*, status: str = "PENDING", max_internal: int = 40):
    m = MagicMock()
    m.id = uuid4()
    m.status = status
    m.max_internal = max_internal
    m.internal1_marks = 10.0
    m.internal2_marks = 10.0
    m.assignment_marks = 8.0
    m.attendance_marks = 4.0
    m.total_internal = None
    return m


def _db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


# ===========================================================================
# 1 — INTERNAL workflow path
# ===========================================================================

class TestInternalWorkflowPath:

    def test_exam_workflow_internal_value(self):
        from app.modules.m08_exam_setter.models import ExamWorkflow
        assert ExamWorkflow.INTERNAL.value == "INTERNAL"

    def test_exam_workflow_board_exam_value(self):
        from app.modules.m08_exam_setter.models import ExamWorkflow
        assert ExamWorkflow.BOARD_EXAM.value == "BOARD_EXAM"

    def test_exam_workflow_enum_has_two_values(self):
        from app.modules.m08_exam_setter.models import ExamWorkflow
        values = {w.value for w in ExamWorkflow}
        assert values == {"INTERNAL", "BOARD_EXAM"}

    @pytest.mark.asyncio
    async def test_submit_for_review_rejects_internal_workflow(self):
        """submit_for_review() must raise INVALID_WORKFLOW for INTERNAL papers."""
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError

        faculty_id = uuid4()
        paper = _paper(workflow="INTERNAL", creator_id=faculty_id)

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.submit_for_review(
                    paper_id=paper.id,
                    faculty_user_id=faculty_id,
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_WORKFLOW"

    @pytest.mark.asyncio
    async def test_faculty_approve_succeeds_on_internal_workflow(self):
        """faculty_approve() must succeed for INTERNAL papers in GENERATED status."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        faculty_id = uuid4()
        paper = _paper(workflow="INTERNAL", status="GENERATED", creator_id=faculty_id)
        updated_paper = _paper(workflow="INTERNAL", status="BOARD_APPROVED")

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, updated_paper]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[MagicMock()]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_faculty_approved",
            new=AsyncMock(),
        ):
            result = await ExamService.faculty_approve(
                paper_id=paper.id,
                payload=FacultyApproveRequest(),
                faculty_user_id=faculty_id,
                db=_db(),
            )
        assert result.status == "BOARD_APPROVED"

    @pytest.mark.asyncio
    async def test_internal_paper_status_after_faculty_approve_is_board_approved(self):
        """INTERNAL workflow Gate 1 should produce BOARD_APPROVED (skips Board review)."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        faculty_id = uuid4()
        paper = _paper(workflow="INTERNAL", status="GENERATED", creator_id=faculty_id)
        approved = _paper(workflow="INTERNAL", status="BOARD_APPROVED")

        set_approved_mock = AsyncMock()
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, approved]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[MagicMock()]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_faculty_approved",
            new=set_approved_mock,
        ):
            await ExamService.faculty_approve(
                paper_id=paper.id,
                payload=FacultyApproveRequest(faculty_comment="Looks good"),
                faculty_user_id=faculty_id,
                db=_db(),
            )
        set_approved_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_internal_workflow_paper_can_be_approved_from_board_returned(self):
        """INTERNAL paper in BOARD_RETURNED can still be faculty_approve()'d."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        faculty_id = uuid4()
        paper = _paper(workflow="INTERNAL", status="BOARD_RETURNED", creator_id=faculty_id)
        updated = _paper(workflow="INTERNAL", status="BOARD_APPROVED")

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, updated]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[MagicMock()]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_faculty_approved",
            new=AsyncMock(),
        ):
            result = await ExamService.faculty_approve(
                paper_id=paper.id,
                payload=FacultyApproveRequest(),
                faculty_user_id=faculty_id,
                db=_db(),
            )
        assert result is not None

    def test_exam_paper_create_schema_accepts_internal_workflow(self):
        from app.modules.m08_exam_setter.schemas import (
            ExamPaperCreate, QuestionFormatConfig, BloomsDistribution,
        )
        from app.modules.m08_exam_setter.models import ExamWorkflow

        ep = ExamPaperCreate(
            course_id=uuid4(),
            title="Internal Test Unit 1",
            total_marks=40,
            duration_mins=90,
            units_included=[1],
            exam_workflow=ExamWorkflow.INTERNAL,
            question_format=QuestionFormatConfig(short_count=4),
            requested_dist=BloomsDistribution(
                remember=25, understand=25, apply=25,
                analyse=15, evaluate=5, create=5,
            ),
        )
        assert ep.exam_workflow == ExamWorkflow.INTERNAL


# ===========================================================================
# 2 — BOARD_EXAM workflow path
# ===========================================================================

class TestBoardExamWorkflowPath:

    @pytest.mark.asyncio
    async def test_faculty_approve_rejects_board_exam_workflow(self):
        """faculty_approve() must raise INVALID_WORKFLOW for BOARD_EXAM papers."""
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        faculty_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", creator_id=faculty_id)

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.faculty_approve(
                    paper_id=paper.id,
                    payload=FacultyApproveRequest(),
                    faculty_user_id=faculty_id,
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_WORKFLOW"

    @pytest.mark.asyncio
    async def test_board_decide_advances_board_exam_paper_to_approved(self):
        """board_decide(approved=True) on a BOARD_EXAM SUBMITTED paper should succeed."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest

        board_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="SUBMITTED")
        approved = _paper(workflow="BOARD_EXAM", status="BOARD_APPROVED")

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, approved]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_board_decision",
            new=AsyncMock(),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[MagicMock()]),
        ), patch(
            "app.modules.m08_exam_setter.service.QuestionBankRepository.promote_from_paper",
            new=AsyncMock(),
        ):
            result = await ExamService.board_decide(
                paper_id=paper.id,
                payload=BoardDecisionRequest(approved=True),
                board_user_id=board_id,
                db=_db(),
            )
        assert result.status == "BOARD_APPROVED"

    @pytest.mark.asyncio
    async def test_board_decide_returns_board_exam_paper_on_rejection(self):
        """board_decide(approved=False) transitions SUBMITTED → BOARD_RETURNED."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest

        board_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="SUBMITTED")
        returned = _paper(workflow="BOARD_EXAM", status="BOARD_RETURNED")

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, returned]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_board_decision",
            new=AsyncMock(),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.modules.m08_exam_setter.service.QuestionBankRepository.promote_from_paper",
            new=AsyncMock(),
        ):
            result = await ExamService.board_decide(
                paper_id=paper.id,
                payload=BoardDecisionRequest(approved=False, board_comment="Needs more analysis questions."),
                board_user_id=board_id,
                db=_db(),
            )
        assert result.status == "BOARD_RETURNED"

    def test_board_exam_is_default_workflow_on_schema(self):
        from app.modules.m08_exam_setter.schemas import ExamPaperCreate
        from app.modules.m08_exam_setter.models import ExamWorkflow
        from app.modules.m08_exam_setter.schemas import QuestionFormatConfig, BloomsDistribution

        ep = ExamPaperCreate(
            course_id=uuid4(),
            title="End Semester Exam 2026",
            total_marks=100,
            duration_mins=180,
            units_included=[1, 2, 3],
            question_format=QuestionFormatConfig(mcq_count=5, long_count=3),
            requested_dist=BloomsDistribution(
                remember=20, understand=20, apply=20,
                analyse=20, evaluate=10, create=10,
            ),
        )
        assert ep.exam_workflow == ExamWorkflow.BOARD_EXAM


# ===========================================================================
# 3 — Faculty approve flow
# ===========================================================================

class TestFacultyApproveFlow:

    @pytest.mark.asyncio
    async def test_faculty_approve_rejects_wrong_creator(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        paper = _paper(workflow="INTERNAL", creator_id=uuid4())
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.faculty_approve(
                    paper_id=paper.id,
                    payload=FacultyApproveRequest(),
                    faculty_user_id=uuid4(),  # different user
                    db=_db(),
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.code == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_faculty_approve_rejects_paper_not_found(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.faculty_approve(
                    paper_id=uuid4(),
                    payload=FacultyApproveRequest(),
                    faculty_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_faculty_approve_rejects_wrong_workflow(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        faculty_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", creator_id=faculty_id)
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.faculty_approve(
                    paper_id=paper.id,
                    payload=FacultyApproveRequest(),
                    faculty_user_id=faculty_id,
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_WORKFLOW"

    @pytest.mark.asyncio
    async def test_faculty_approve_rejects_invalid_status_draft(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        faculty_id = uuid4()
        paper = _paper(workflow="INTERNAL", status="DRAFT", creator_id=faculty_id)
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.faculty_approve(
                    paper_id=paper.id,
                    payload=FacultyApproveRequest(),
                    faculty_user_id=faculty_id,
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_faculty_approve_rejects_invalid_status_submitted(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        faculty_id = uuid4()
        paper = _paper(workflow="INTERNAL", status="SUBMITTED", creator_id=faculty_id)
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.faculty_approve(
                    paper_id=paper.id,
                    payload=FacultyApproveRequest(),
                    faculty_user_id=faculty_id,
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_faculty_approve_rejects_no_questions(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest

        faculty_id = uuid4()
        paper = _paper(workflow="INTERNAL", status="GENERATED", creator_id=faculty_id)
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[]),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.faculty_approve(
                    paper_id=paper.id,
                    payload=FacultyApproveRequest(),
                    faculty_user_id=faculty_id,
                    db=_db(),
                )
            assert exc_info.value.code == "NO_QUESTIONS"

    def test_faculty_approve_request_schema_optional_comment(self):
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest
        req = FacultyApproveRequest()
        assert req.faculty_comment is None

    def test_faculty_approve_request_schema_with_comment(self):
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest
        req = FacultyApproveRequest(faculty_comment="All questions verified.")
        assert req.faculty_comment == "All questions verified."

    def test_faculty_approve_request_schema_accepts_empty_dict(self):
        """Simulates frontend sending {} — body must parse without 422."""
        from app.modules.m08_exam_setter.schemas import FacultyApproveRequest
        req = FacultyApproveRequest.model_validate({})
        assert req.faculty_comment is None


# ===========================================================================
# 4 — Scrutinizer flow
# ===========================================================================

class TestScrutinizerFlow:

    @pytest.mark.asyncio
    async def test_assign_scrutinizer_rejects_internal_workflow(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import ScrutinizerAssignRequest

        paper = _paper(workflow="INTERNAL", status="SUBMITTED")
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.assign_scrutinizer(
                    paper_id=paper.id,
                    payload=ScrutinizerAssignRequest(scrutinizer_id=uuid4()),
                    assigning_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_WORKFLOW"

    @pytest.mark.asyncio
    async def test_assign_scrutinizer_rejects_non_submitted_status(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import ScrutinizerAssignRequest

        paper = _paper(workflow="BOARD_EXAM", status="GENERATED")
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.assign_scrutinizer(
                    paper_id=paper.id,
                    payload=ScrutinizerAssignRequest(scrutinizer_id=uuid4()),
                    assigning_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_assign_scrutinizer_rejects_paper_not_found(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import ScrutinizerAssignRequest

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.assign_scrutinizer(
                    paper_id=uuid4(),
                    payload=ScrutinizerAssignRequest(scrutinizer_id=uuid4()),
                    assigning_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_assign_scrutinizer_succeeds_for_submitted_board_exam(self):
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import ScrutinizerAssignRequest

        scrutinizer_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="SUBMITTED")
        updated = _paper(workflow="BOARD_EXAM", status="SUBMITTED")
        updated.scrutinizer_id = scrutinizer_id

        set_scrut_mock = AsyncMock()
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, updated]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_scrutinizer",
            new=set_scrut_mock,
        ):
            await ExamService.assign_scrutinizer(
                paper_id=paper.id,
                payload=ScrutinizerAssignRequest(scrutinizer_id=scrutinizer_id),
                assigning_user_id=uuid4(),
                db=_db(),
            )
        set_scrut_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scrutinize_rejects_wrong_scrutinizer(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import ScrutinizerDecisionRequest

        assigned_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="SUBMITTED", scrutinizer_id=assigned_id)

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.scrutinize(
                    paper_id=paper.id,
                    payload=ScrutinizerDecisionRequest(approved=True),
                    scrutinizer_user_id=uuid4(),  # different user
                    db=_db(),
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.code == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_scrutinize_rejects_invalid_status(self):
        from app.modules.m08_exam_setter.service import ExamService, ExamServiceError
        from app.modules.m08_exam_setter.schemas import ScrutinizerDecisionRequest

        scrut_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="GENERATED", scrutinizer_id=scrut_id)

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(return_value=paper),
        ):
            with pytest.raises(ExamServiceError) as exc_info:
                await ExamService.scrutinize(
                    paper_id=paper.id,
                    payload=ScrutinizerDecisionRequest(approved=True),
                    scrutinizer_user_id=scrut_id,
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_scrutinize_approval_keeps_submitted_status(self):
        """Scrutinizer approval keeps paper SUBMITTED for Board to decide."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import ScrutinizerDecisionRequest

        scrut_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="SUBMITTED", scrutinizer_id=scrut_id)
        still_submitted = _paper(workflow="BOARD_EXAM", status="SUBMITTED")

        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, still_submitted]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_scrutinized",
            new=AsyncMock(),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_status",
            new=AsyncMock(),
        ) as set_status_mock:
            await ExamService.scrutinize(
                paper_id=paper.id,
                payload=ScrutinizerDecisionRequest(approved=True),
                scrutinizer_user_id=scrut_id,
                db=_db(),
            )
        # set_status should NOT be called on approval (paper stays SUBMITTED)
        set_status_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_scrutinize_rejection_calls_set_status_board_returned(self):
        """Scrutinizer rejection must call set_status(BOARD_RETURNED)."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import ScrutinizerDecisionRequest
        from app.modules.m08_exam_setter.models import ExamPaperStatus

        scrut_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="SUBMITTED", scrutinizer_id=scrut_id)
        returned = _paper(workflow="BOARD_EXAM", status="BOARD_RETURNED")

        set_status_mock = AsyncMock()
        db = _db()  # capture once so the same object is compared
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, returned]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_scrutinized",
            new=AsyncMock(),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_status",
            new=set_status_mock,
        ):
            await ExamService.scrutinize(
                paper_id=paper.id,
                payload=ScrutinizerDecisionRequest(
                    approved=False, scrutinizer_comment="Q5 is ambiguous."
                ),
                scrutinizer_user_id=scrut_id,
                db=db,
            )
        # Verify set_status was called with BOARD_RETURNED
        set_status_mock.assert_awaited_once()
        call_args = set_status_mock.call_args
        assert call_args[0][1] == ExamPaperStatus.BOARD_RETURNED.value

    def test_scrutinizer_decision_schema_rejects_return_without_comment(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import ScrutinizerDecisionRequest
        with pytest.raises(pydantic.ValidationError):
            ScrutinizerDecisionRequest(approved=False)  # missing scrutinizer_comment

    def test_scrutinizer_decision_schema_return_with_comment_passes(self):
        from app.modules.m08_exam_setter.schemas import ScrutinizerDecisionRequest
        req = ScrutinizerDecisionRequest(approved=False, scrutinizer_comment="Needs work.")
        assert req.scrutinizer_comment == "Needs work."


# ===========================================================================
# 5 — Question regeneration flow
# ===========================================================================

class TestRegenerationFlow:

    def test_regenerate_exam_question_worker_importable(self):
        from app.workers.heavy.regenerate_exam_question import regenerate_exam_question
        assert callable(regenerate_exam_question)

    def test_regenerate_exam_question_task_name(self):
        from app.workers.heavy.regenerate_exam_question import regenerate_exam_question
        assert regenerate_exam_question.name == "app.workers.heavy.regenerate_exam_question"

    def test_regenerate_task_registered_in_celery_include(self):
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.regenerate_exam_question" in include

    def test_regenerate_router_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/questions/{question_id}/regenerate" in paths

    def test_regenerate_question_request_schema_optional_instruction(self):
        from app.modules.m08_exam_setter.schemas import RegenerateQuestionRequest
        req = RegenerateQuestionRequest()
        assert req.instruction is None

    def test_regenerate_question_request_schema_with_instruction(self):
        from app.modules.m08_exam_setter.schemas import RegenerateQuestionRequest
        req = RegenerateQuestionRequest(instruction="Use a real-world engineering scenario.")
        assert "engineering" in req.instruction

    def test_regenerate_multiple_tasks_not_regressed(self):
        """Both generate and regenerate tasks must be registered."""
        from app.workers.celery_app import celery_app
        include = celery_app.conf.include
        assert "app.workers.heavy.generate_exam_paper" in include
        assert "app.workers.heavy.regenerate_exam_question" in include

    def test_with_answers_endpoint_present(self):
        """Board needs /questions/with-answers endpoint for model answers view."""
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/questions/with-answers" in paths


# ===========================================================================
# 6 — Question bank promotion on board approval
# ===========================================================================

class TestQuestionBankPromotion:

    @pytest.mark.asyncio
    async def test_board_approve_calls_promote_from_paper(self):
        """board_decide(approved=True) must call QuestionBankRepository.promote_from_paper."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest

        board_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="SUBMITTED")
        approved = _paper(workflow="BOARD_EXAM", status="BOARD_APPROVED")

        promote_mock = AsyncMock()
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, approved]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_board_decision",
            new=AsyncMock(),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[MagicMock(), MagicMock()]),
        ), patch(
            "app.modules.m08_exam_setter.service.QuestionBankRepository.promote_from_paper",
            new=promote_mock,
        ):
            await ExamService.board_decide(
                paper_id=paper.id,
                payload=BoardDecisionRequest(approved=True),
                board_user_id=board_id,
                db=_db(),
            )
        promote_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_board_reject_does_not_call_promote_from_paper(self):
        """board_decide(approved=False) must NOT promote questions to the bank."""
        from app.modules.m08_exam_setter.service import ExamService
        from app.modules.m08_exam_setter.schemas import BoardDecisionRequest

        board_id = uuid4()
        paper = _paper(workflow="BOARD_EXAM", status="SUBMITTED")
        returned = _paper(workflow="BOARD_EXAM", status="BOARD_RETURNED")

        promote_mock = AsyncMock()
        with patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.get_by_id",
            new=AsyncMock(side_effect=[paper, returned]),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamPaperRepository.set_board_decision",
            new=AsyncMock(),
        ), patch(
            "app.modules.m08_exam_setter.service.ExamQuestionRepository.list_by_paper",
            new=AsyncMock(return_value=[MagicMock()]),
        ), patch(
            "app.modules.m08_exam_setter.service.QuestionBankRepository.promote_from_paper",
            new=promote_mock,
        ):
            await ExamService.board_decide(
                paper_id=paper.id,
                payload=BoardDecisionRequest(
                    approved=False, board_comment="Not enough analysis questions."
                ),
                board_user_id=board_id,
                db=_db(),
            )
        promote_mock.assert_not_awaited()

    def test_question_bank_entry_model_importable(self):
        from app.modules.m08_exam_setter.models import QuestionBankEntry
        assert QuestionBankEntry.__tablename__ == "question_bank"

    def test_question_bank_entry_response_schema_importable(self):
        from app.modules.m08_exam_setter.schemas import QuestionBankEntryResponse
        assert QuestionBankEntryResponse is not None

    def test_question_bank_list_response_schema_importable(self):
        from app.modules.m08_exam_setter.schemas import QuestionBankListResponse
        assert QuestionBankListResponse is not None

    def test_question_bank_repository_importable(self):
        from app.modules.m08_exam_setter.repository import QuestionBankRepository
        assert hasattr(QuestionBankRepository, "promote_from_paper")
        assert hasattr(QuestionBankRepository, "list_by_course")

    def test_question_bank_browse_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/question-bank/{course_id}" in paths

    def test_question_bank_promoted_audit_event_present(self):
        from app.core.audit_log.models import AuditEventType
        assert hasattr(AuditEventType, "QUESTION_BANK_PROMOTED")


# ===========================================================================
# 7 — Internal marks submit gate
# ===========================================================================

class TestInternalMarksSubmitGate:

    def test_internal_mark_status_enum_values(self):
        from app.modules.m08_exam_setter.models import InternalMarkStatus
        values = {s.value for s in InternalMarkStatus}
        assert values == {"PENDING", "FACULTY_SUBMITTED", "DEAN_LOCKED"}

    @pytest.mark.asyncio
    async def test_submit_rejects_record_not_found(self):
        from app.modules.m08_exam_setter.service import InternalMarksService, InternalMarksServiceError

        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(InternalMarksServiceError) as exc_info:
                await InternalMarksService.submit(
                    ims_id=uuid4(),
                    faculty_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_rejects_non_pending_status(self):
        from app.modules.m08_exam_setter.service import InternalMarksService, InternalMarksServiceError

        record = _ims(status="FACULTY_SUBMITTED")
        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(return_value=record),
        ):
            with pytest.raises(InternalMarksServiceError) as exc_info:
                await InternalMarksService.submit(
                    ims_id=record.id,
                    faculty_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_submit_rejects_total_exceeds_max(self):
        from app.modules.m08_exam_setter.service import InternalMarksService, InternalMarksServiceError

        record = _ims(status="PENDING", max_internal=20)
        record.internal1_marks = 10.0
        record.internal2_marks = 10.0
        record.assignment_marks = 5.0
        record.attendance_marks = 5.0  # total = 30 > max 20

        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(return_value=record),
        ):
            with pytest.raises(InternalMarksServiceError) as exc_info:
                await InternalMarksService.submit(
                    ims_id=record.id,
                    faculty_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.code == "TOTAL_EXCEEDS_MAX"

    @pytest.mark.asyncio
    async def test_submit_computes_total_internal_correctly(self):
        """submit() must compute total = sum of non-null components."""
        from app.modules.m08_exam_setter.service import InternalMarksService

        record = _ims(status="PENDING", max_internal=40)
        record.internal1_marks  = 12.0
        record.internal2_marks  = 14.0
        record.assignment_marks = 8.0
        record.attendance_marks = None  # null component excluded from sum
        # expected total = 12 + 14 + 8 = 34

        updated = _ims(status="FACULTY_SUBMITTED")
        updated.total_internal = 34.0

        set_submitted_mock = AsyncMock()
        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(side_effect=[record, updated]),
        ), patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.set_submitted",
            new=set_submitted_mock,
        ):
            await InternalMarksService.submit(
                ims_id=record.id,
                faculty_user_id=uuid4(),
                db=_db(),
            )
        # Verify set_submitted was called with total = 34
        call_kwargs = set_submitted_mock.call_args.kwargs
        assert call_kwargs["total_internal"] == pytest.approx(34.0)

    @pytest.mark.asyncio
    async def test_submit_transitions_to_faculty_submitted(self):
        from app.modules.m08_exam_setter.service import InternalMarksService

        record = _ims(status="PENDING", max_internal=40)
        submitted = _ims(status="FACULTY_SUBMITTED")

        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(side_effect=[record, submitted]),
        ), patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.set_submitted",
            new=AsyncMock(),
        ):
            result = await InternalMarksService.submit(
                ims_id=record.id,
                faculty_user_id=uuid4(),
                db=_db(),
            )
        assert result.status == "FACULTY_SUBMITTED"

    def test_internal_marks_submit_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/internal-marks/{ims_id}/submit" in paths

    def test_internal_marks_submitted_audit_event_present(self):
        from app.core.audit_log.models import AuditEventType
        assert hasattr(AuditEventType, "INTERNAL_MARKS_SUBMITTED")

    def test_internal_marks_response_schema_importable(self):
        from app.modules.m08_exam_setter.schemas import InternalMarksResponse
        assert InternalMarksResponse is not None

    def test_internal_marks_list_response_schema_importable(self):
        from app.modules.m08_exam_setter.schemas import InternalMarksListResponse
        assert InternalMarksListResponse is not None


# ===========================================================================
# 8 — Internal marks Dean lock gate
# ===========================================================================

class TestInternalMarksDeanLockGate:

    @pytest.mark.asyncio
    async def test_lock_rejects_record_not_found(self):
        from app.modules.m08_exam_setter.service import InternalMarksService, InternalMarksServiceError

        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(InternalMarksServiceError) as exc_info:
                await InternalMarksService.lock(
                    ims_id=uuid4(),
                    dean_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_lock_rejects_pending_status(self):
        """Lock gate requires FACULTY_SUBMITTED — must reject PENDING."""
        from app.modules.m08_exam_setter.service import InternalMarksService, InternalMarksServiceError

        record = _ims(status="PENDING")
        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(return_value=record),
        ):
            with pytest.raises(InternalMarksServiceError) as exc_info:
                await InternalMarksService.lock(
                    ims_id=record.id,
                    dean_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_lock_rejects_already_locked(self):
        from app.modules.m08_exam_setter.service import InternalMarksService, InternalMarksServiceError

        record = _ims(status="DEAN_LOCKED")
        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(return_value=record),
        ):
            with pytest.raises(InternalMarksServiceError) as exc_info:
                await InternalMarksService.lock(
                    ims_id=record.id,
                    dean_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_lock_succeeds_on_faculty_submitted(self):
        from app.modules.m08_exam_setter.service import InternalMarksService

        record = _ims(status="FACULTY_SUBMITTED")
        locked = _ims(status="DEAN_LOCKED")

        set_locked_mock = AsyncMock()
        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_id",
            new=AsyncMock(side_effect=[record, locked]),
        ), patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.set_locked",
            new=set_locked_mock,
        ):
            result = await InternalMarksService.lock(
                ims_id=record.id,
                dean_user_id=uuid4(),
                db=_db(),
            )
        assert result.status == "DEAN_LOCKED"
        set_locked_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_or_update_rejects_locked_record(self):
        from app.modules.m08_exam_setter.service import InternalMarksService, InternalMarksServiceError
        from app.modules.m08_exam_setter.schemas import InternalMarksCreate

        locked_record = _ims(status="DEAN_LOCKED")
        payload = InternalMarksCreate(
            student_id=uuid4(),
            course_id=uuid4(),
            semester=1,
            academic_year="2025-26",
            internal1_marks=10.0,
        )

        with patch(
            "app.modules.m08_exam_setter.service.InternalMarksRepository.get_by_student_course",
            new=AsyncMock(return_value=locked_record),
        ):
            with pytest.raises(InternalMarksServiceError) as exc_info:
                await InternalMarksService.create_or_update(
                    payload=payload,
                    faculty_user_id=uuid4(),
                    db=_db(),
                )
            assert exc_info.value.code == "LOCKED"
            assert exc_info.value.status_code == 403

    def test_internal_marks_lock_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/internal-marks/{ims_id}/lock" in paths

    def test_internal_marks_locked_audit_event_present(self):
        from app.core.audit_log.models import AuditEventType
        assert hasattr(AuditEventType, "INTERNAL_MARKS_LOCKED")

    def test_dean_role_group_in_router(self):
        from app.modules.m08_exam_setter.router import _DEAN
        from app.core.auth.models import TenantRole
        assert TenantRole.DEAN in _DEAN
        assert TenantRole.ADMIN in _DEAN


# ===========================================================================
# 9 — CO coverage report generation
# ===========================================================================

class TestCOCoverageReport:

    def _cov(self):
        from app.workers.heavy.generate_exam_paper import _compute_co_coverage
        return _compute_co_coverage

    def test_empty_cos_returns_empty_report_and_true(self):
        fn = self._cov()
        report, ok = fn(questions=[], course_outcomes=[])
        assert report == []
        assert ok is True

    def test_all_cos_covered_returns_true(self):
        fn = self._cov()
        co_id = str(uuid4())
        questions = [{"co_ids": [co_id], "unit_number": 1, "marks": 5}]
        cos = [{"id": co_id, "co_code": "CO1"}]
        report, ok = fn(questions, cos)
        assert ok is True

    def test_missing_co_returns_false(self):
        fn = self._cov()
        co1_id = str(uuid4())
        co2_id = str(uuid4())
        questions = [{"co_ids": [co1_id], "unit_number": 1, "marks": 5}]
        cos = [
            {"id": co1_id, "co_code": "CO1"},
            {"id": co2_id, "co_code": "CO2"},  # not covered
        ]
        report, ok = fn(questions, cos)
        assert ok is False

    def test_report_contains_correct_question_count(self):
        fn = self._cov()
        co_id = str(uuid4())
        questions = [
            {"co_ids": [co_id], "unit_number": 1, "marks": 5},
            {"co_ids": [co_id], "unit_number": 2, "marks": 5},
            {"co_ids": [],      "unit_number": 1, "marks": 5},
        ]
        cos = [{"id": co_id, "co_code": "CO1"}]
        report, ok = fn(questions, cos)
        co_entry = next(e for e in report if e["co_id"] == co_id)
        assert co_entry["question_count"] == 2
        assert co_entry["covered"] is True

    def test_report_entry_has_required_fields(self):
        fn = self._cov()
        co_id = str(uuid4())
        questions = [{"co_ids": [co_id], "unit_number": 1, "marks": 5}]
        cos = [{"id": co_id, "co_code": "CO-TEST"}]
        report, _ = fn(questions, cos)
        assert len(report) == 1
        entry = report[0]
        assert "co_id" in entry
        assert "co_code" in entry
        assert "covered" in entry
        assert "question_count" in entry

    def test_co_code_preserved_in_report(self):
        fn = self._cov()
        co_id = str(uuid4())
        questions = [{"co_ids": [co_id], "unit_number": 1, "marks": 5}]
        cos = [{"id": co_id, "co_code": "CO-PRESERVED"}]
        report, _ = fn(questions, cos)
        assert report[0]["co_code"] == "CO-PRESERVED"

    def test_questions_without_co_ids_not_counted(self):
        fn = self._cov()
        co_id = str(uuid4())
        questions = [
            {"co_ids": None, "unit_number": 1, "marks": 5},
            {"co_ids": [],   "unit_number": 2, "marks": 5},
        ]
        cos = [{"id": co_id, "co_code": "CO1"}]
        report, ok = fn(questions, cos)
        assert ok is False
        assert report[0]["question_count"] == 0

    def test_multiple_cos_partial_coverage(self):
        fn = self._cov()
        co1_id = str(uuid4())
        co2_id = str(uuid4())
        co3_id = str(uuid4())
        questions = [
            {"co_ids": [co1_id, co2_id], "unit_number": 1, "marks": 5},
        ]
        cos = [
            {"id": co1_id, "co_code": "CO1"},
            {"id": co2_id, "co_code": "CO2"},
            {"id": co3_id, "co_code": "CO3"},  # uncovered
        ]
        report, ok = fn(questions, cos)
        assert ok is False
        covered = [e["co_code"] for e in report if e["covered"]]
        assert set(covered) == {"CO1", "CO2"}

    def test_coverage_endpoint_present_in_router(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/coverage" in paths

    def test_co_coverage_ok_field_on_blooms_report_model(self):
        from app.modules.m08_exam_setter.models import BloomsComplianceReport
        import inspect
        src = inspect.getsource(BloomsComplianceReport)
        assert "co_coverage_ok" in src

    def test_unit_coverage_ok_field_on_blooms_report_model(self):
        from app.modules.m08_exam_setter.models import BloomsComplianceReport
        import inspect
        src = inspect.getsource(BloomsComplianceReport)
        assert "unit_coverage_ok" in src


# ===========================================================================
# 10 — Unit coverage report generation
# ===========================================================================

class TestUnitCoverageReport:

    def _cov(self):
        from app.workers.heavy.generate_exam_paper import _compute_unit_coverage
        return _compute_unit_coverage

    def test_empty_units_returns_empty_report_and_true(self):
        fn = self._cov()
        report, ok = fn(questions=[], units_included=[])
        assert report == []
        assert ok is True

    def test_all_units_covered_returns_true(self):
        fn = self._cov()
        questions = [
            {"unit_number": 1, "marks": 5},
            {"unit_number": 2, "marks": 5},
        ]
        report, ok = fn(questions, [1, 2])
        assert ok is True

    def test_missing_unit_returns_false(self):
        fn = self._cov()
        questions = [{"unit_number": 1, "marks": 5}]
        report, ok = fn(questions, [1, 2, 3])
        assert ok is False

    def test_report_correct_question_count_per_unit(self):
        fn = self._cov()
        questions = [
            {"unit_number": 1, "marks": 5},
            {"unit_number": 1, "marks": 5},
            {"unit_number": 2, "marks": 5},
        ]
        report, _ = fn(questions, [1, 2])
        u1 = next(e for e in report if e["unit_no"] == 1)
        u2 = next(e for e in report if e["unit_no"] == 2)
        assert u1["question_count"] == 2
        assert u2["question_count"] == 1

    def test_report_entry_has_required_fields(self):
        fn = self._cov()
        questions = [{"unit_number": 1, "marks": 5}]
        report, _ = fn(questions, [1])
        assert len(report) == 1
        entry = report[0]
        assert "unit_no" in entry
        assert "covered" in entry
        assert "question_count" in entry

    def test_report_sorted_by_unit_number(self):
        fn = self._cov()
        questions = [
            {"unit_number": 3, "marks": 5},
            {"unit_number": 1, "marks": 5},
            {"unit_number": 2, "marks": 5},
        ]
        report, _ = fn(questions, [1, 2, 3])
        unit_numbers = [e["unit_no"] for e in report]
        assert unit_numbers == sorted(unit_numbers)

    def test_duplicate_units_in_included_deduplicated(self):
        fn = self._cov()
        questions = [{"unit_number": 1, "marks": 5}]
        report, _ = fn(questions, [1, 1, 1])  # duplicates
        # Only one entry per unit
        assert len(report) == 1

    def test_uncovered_unit_has_zero_count(self):
        fn = self._cov()
        questions = [{"unit_number": 1, "marks": 5}]
        report, _ = fn(questions, [1, 2])
        u2 = next(e for e in report if e["unit_no"] == 2)
        assert u2["question_count"] == 0
        assert u2["covered"] is False

    def test_covered_flag_true_when_count_positive(self):
        fn = self._cov()
        questions = [{"unit_number": 5, "marks": 10}]
        report, _ = fn(questions, [5])
        assert report[0]["covered"] is True


# ===========================================================================
# 11 — H-35 Schema validators
# ===========================================================================

class TestH35Schemas:

    def test_section_config_answer_q_cannot_exceed_total_q(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import SectionConfig
        with pytest.raises(pydantic.ValidationError):
            SectionConfig(label="A", total_q=5, answer_q=8, marks_each=2, order=0)

    def test_section_config_answer_q_equals_total_q_passes(self):
        from app.modules.m08_exam_setter.schemas import SectionConfig
        sc = SectionConfig(label="A", total_q=5, answer_q=5, marks_each=2, order=0)
        assert sc.total_q == 5

    def test_section_config_mcq_only_defaults_false(self):
        from app.modules.m08_exam_setter.schemas import SectionConfig
        sc = SectionConfig(label="B", total_q=3, answer_q=3, marks_each=5, order=1)
        assert sc.mcq_only is False

    def test_exam_paper_create_mcq_guard_section_mcq_only_without_mcq_count(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import (
            ExamPaperCreate, QuestionFormatConfig, BloomsDistribution, SectionConfig,
        )
        with pytest.raises(pydantic.ValidationError):
            ExamPaperCreate(
                course_id=uuid4(),
                title="Bad Config",
                total_marks=100,
                duration_mins=120,
                units_included=[1],
                question_format=QuestionFormatConfig(short_count=5, mcq_count=0),
                requested_dist=BloomsDistribution(
                    remember=20, understand=20, apply=20,
                    analyse=20, evaluate=10, create=10,
                ),
                section_config=[
                    SectionConfig(label="A", total_q=5, answer_q=5, marks_each=2, order=0,
                                  mcq_only=True),  # mcq_only=True but mcq_count=0
                ],
            )

    def test_internal_marks_create_schema_validates_semester_range(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import InternalMarksCreate
        with pytest.raises(pydantic.ValidationError):
            InternalMarksCreate(
                student_id=uuid4(),
                course_id=uuid4(),
                semester=0,  # must be > 0
                academic_year="2025-26",
            )

    def test_internal_marks_create_schema_valid_passes(self):
        from app.modules.m08_exam_setter.schemas import InternalMarksCreate
        ims = InternalMarksCreate(
            student_id=uuid4(),
            course_id=uuid4(),
            semester=3,
            academic_year="2025-26",
            internal1_marks=15.0,
            internal2_marks=16.0,
            assignment_marks=8.0,
            attendance_marks=5.0,
            max_internal=50,
        )
        assert ims.semester == 3

    def test_scrutinizer_assign_request_requires_uuid(self):
        import pydantic
        from app.modules.m08_exam_setter.schemas import ScrutinizerAssignRequest
        with pytest.raises(pydantic.ValidationError):
            ScrutinizerAssignRequest(scrutinizer_id="not-a-uuid")

    def test_scrutinizer_assign_request_valid_passes(self):
        from app.modules.m08_exam_setter.schemas import ScrutinizerAssignRequest
        req = ScrutinizerAssignRequest(scrutinizer_id=uuid4())
        assert req.scrutinizer_id is not None


# ===========================================================================
# 12 — H-35 Router wiring
# ===========================================================================

class TestH35RouterWiring:

    def test_faculty_approve_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/faculty-approve" in paths

    def test_faculty_approve_payload_has_default(self):
        """Endpoint body must default so frontend can POST with empty body."""
        import inspect
        from app.modules.m08_exam_setter.router import faculty_approve
        sig = inspect.signature(faculty_approve)
        param = sig.parameters.get("payload")
        assert param is not None
        assert param.default is not inspect.Parameter.empty

    def test_assign_scrutinizer_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/assign-scrutinizer" in paths

    def test_scrutinize_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/scrutinize" in paths

    def test_sections_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/{paper_id}/sections" in paths

    def test_internal_marks_create_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/internal-marks" in paths

    def test_internal_marks_by_course_endpoint_present(self):
        from app.modules.m08_exam_setter.router import router
        paths = {r.path for r in router.routes}
        assert "/internal-marks/course/{course_id}" in paths

    def test_router_has_at_least_20_routes(self):
        """H-35 added 9+ routes; total must be at least 20."""
        from app.modules.m08_exam_setter.router import router
        assert len(router.routes) >= 20

    def test_h35_audit_events_all_present(self):
        from app.core.audit_log.models import AuditEventType
        h35_events = [
            "EXAM_PAPER_AUTO_RELEASED",
            "EXAM_PAPER_EXPORT_PDF",
            "EXAM_PAPER_FACULTY_APPROVED",
            "EXAM_PAPER_SCRUTINIZER_ASSIGNED",
            "EXAM_PAPER_SCRUTINIZED",
            "EXAM_PAPER_SECTION_CONFIGURED",
            "EXAM_PAPER_QUESTION_REGENERATED",
            "EXAM_PAPER_CO_COVERAGE_COMPUTED",
            "QUESTION_BANK_PROMOTED",
            "INTERNAL_MARKS_SUBMITTED",
            "INTERNAL_MARKS_LOCKED",
        ]
        for name in h35_events:
            assert hasattr(AuditEventType, name), f"Missing H-35 audit event: {name}"


# ===========================================================================
# 13 — H-35 Models
# ===========================================================================

class TestH35Models:

    def test_internal_marks_summary_model_importable(self):
        from app.modules.m08_exam_setter.models import InternalMarksSummary
        assert InternalMarksSummary.__tablename__ == "internal_marks_summary"

    def test_question_bank_entry_has_is_approved_column(self):
        from app.modules.m08_exam_setter.models import QuestionBankEntry
        import inspect
        src = inspect.getsource(QuestionBankEntry)
        assert "is_approved" in src

    def test_question_bank_entry_has_usage_count_column(self):
        from app.modules.m08_exam_setter.models import QuestionBankEntry
        import inspect
        src = inspect.getsource(QuestionBankEntry)
        assert "usage_count" in src

    def test_exam_paper_has_exam_workflow_column(self):
        from app.modules.m08_exam_setter.models import ExamPaper
        import inspect
        src = inspect.getsource(ExamPaper)
        assert "exam_workflow" in src

    def test_exam_paper_has_section_config_column(self):
        from app.modules.m08_exam_setter.models import ExamPaper
        import inspect
        src = inspect.getsource(ExamPaper)
        assert "section_config" in src

    def test_exam_paper_has_co_coverage_report_column(self):
        from app.modules.m08_exam_setter.models import ExamPaper
        import inspect
        src = inspect.getsource(ExamPaper)
        assert "co_coverage_report" in src

    def test_exam_question_has_section_label_column(self):
        from app.modules.m08_exam_setter.models import ExamQuestion
        import inspect
        src = inspect.getsource(ExamQuestion)
        assert "section_label" in src

    def test_exam_question_has_co_ids_column(self):
        from app.modules.m08_exam_setter.models import ExamQuestion
        import inspect
        src = inspect.getsource(ExamQuestion)
        assert "co_ids" in src

    def test_exam_question_has_choice_group_column(self):
        from app.modules.m08_exam_setter.models import ExamQuestion
        import inspect
        src = inspect.getsource(ExamQuestion)
        assert "choice_group" in src

    def test_internal_marks_service_error_importable(self):
        from app.modules.m08_exam_setter.service import InternalMarksServiceError
        err = InternalMarksServiceError("LOCKED", "Locked.", 403)
        assert err.status_code == 403

    def test_internal_marks_repository_has_required_methods(self):
        from app.modules.m08_exam_setter.repository import InternalMarksRepository
        assert hasattr(InternalMarksRepository, "create")
        assert hasattr(InternalMarksRepository, "get_by_id")
        assert hasattr(InternalMarksRepository, "set_submitted")
        assert hasattr(InternalMarksRepository, "set_locked")
        assert hasattr(InternalMarksRepository, "list_by_course")
