"""
M09.8 Examination Analytics — service orchestration.

Each method follows the same reusable pipeline:
    load normalised rows (repository)  →  compute (pure functions)  →  enrich
    with human-readable labels  →  wrap in response schemas.

The service holds no maths and no SQL of its own — it is the seam where the
two reusable halves (compute + repository) meet.  New analytics categories are
added by composing the same three steps.

Read-only.  No method here mutates exam data.  ("AI advises, humans decide.")
"""
from __future__ import annotations

import statistics
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin import analytics_compute as compute
from app.modules.m09_paper_admin.analytics_repository import AnalyticsRepository
from app.modules.m09_paper_admin.analytics_schemas import (
    BatchAnalyticsResponse,
    BatchStatResponse,
    DashboardResponse,
    FacultyAnalyticsResponse,
    FacultyStatResponse,
    GradeAnalyticsResponse,
    GradeBucketResponse,
    ModerationAnalyticsResponse,
    OverviewResponse,
    RevaluationAnalyticsResponse,
    SubjectAnalyticsResponse,
    SubjectStatResponse,
)


class ExamAnalyticsService:

    # -----------------------------------------------------------------------
    # Examination Overview
    # -----------------------------------------------------------------------

    @staticmethod
    async def overview(
        exam_paper_id: UUID | None,
        *,
        pass_pct: float = compute.DEFAULT_PASS_PCT,
        db: AsyncSession,
    ) -> OverviewResponse:
        rows = await AnalyticsRepository.load_score_rows(exam_paper_id, db=db)
        stats = compute.compute_overview(rows, pass_pct=pass_pct)

        paper_ids = {r.exam_paper_id for r in rows}
        title = None
        if exam_paper_id:
            labels = await AnalyticsRepository.load_paper_labels([str(exam_paper_id)], db=db)
            title = labels.get(str(exam_paper_id), {}).get("title")

        return OverviewResponse(
            scope="PAPER" if exam_paper_id else "INSTITUTION",
            exam_paper_id=str(exam_paper_id) if exam_paper_id else None,
            exam_paper_title=title,
            total_students=stats.total_students,
            appeared=stats.appeared,
            absent=stats.absent,
            pass_count=stats.pass_count,
            fail_count=stats.fail_count,
            pass_pct=stats.pass_pct,
            average_pct=stats.average_pct,
            highest_pct=stats.highest_pct,
            lowest_pct=stats.lowest_pct,
            pass_threshold_pct=stats.pass_threshold_pct,
            papers_count=len(paper_ids),
        )

    # -----------------------------------------------------------------------
    # Subject Analytics
    # -----------------------------------------------------------------------

    @staticmethod
    async def subjects(
        exam_paper_id: UUID | None,
        *,
        pass_pct: float = compute.DEFAULT_PASS_PCT,
        db: AsyncSession,
    ) -> SubjectAnalyticsResponse:
        rows = await AnalyticsRepository.load_score_rows(exam_paper_id, db=db)
        stats = compute.compute_subject_stats(rows, pass_pct=pass_pct)

        paper_labels = await AnalyticsRepository.load_paper_labels(
            [s.exam_paper_id for s in stats], db=db
        )
        course_ids = [
            paper_labels.get(s.exam_paper_id, {}).get("course_id")
            for s in stats
        ]
        course_labels = await AnalyticsRepository.load_course_labels(
            [c for c in course_ids if c], db=db
        )

        subjects: list[SubjectStatResponse] = []
        for s in stats:
            pl = paper_labels.get(s.exam_paper_id, {})
            cl = course_labels.get(pl.get("course_id") or "", {})
            subjects.append(SubjectStatResponse(
                exam_paper_id=s.exam_paper_id,
                exam_paper_title=pl.get("title"),
                course_code=cl.get("code"),
                course_title=cl.get("title"),
                count=s.count,
                average=s.average,
                median=s.median,
                highest=s.highest,
                lowest=s.lowest,
                pass_count=s.pass_count,
                fail_count=s.fail_count,
                pass_pct=s.pass_pct,
                fail_pct=s.fail_pct,
            ))

        return SubjectAnalyticsResponse(
            pass_threshold_pct=pass_pct,
            subjects=subjects,
        )

    # -----------------------------------------------------------------------
    # Faculty Analytics
    # -----------------------------------------------------------------------

    @staticmethod
    async def faculty(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> FacultyAnalyticsResponse:
        rows = await AnalyticsRepository.load_eval_rows(exam_paper_id, db=db)
        stats = compute.compute_faculty_stats(rows)

        names = await AnalyticsRepository.load_user_names(
            [s.evaluator_id for s in stats], db=db
        )

        # Institution benchmark = mean of per-faculty average awarded %
        bench_vals = [s.average_awarded_pct for s in stats if s.average_awarded_pct is not None]
        benchmark = round(statistics.mean(bench_vals), 1) if bench_vals else None

        faculty = [
            FacultyStatResponse(
                evaluator_id=s.evaluator_id,
                evaluator_name=names.get(s.evaluator_id),
                scripts_evaluated=s.scripts_evaluated,
                average_awarded_pct=s.average_awarded_pct,
                average_awarded_marks=s.average_awarded_marks,
                avg_turnaround_hours=s.avg_turnaround_hours,
            )
            for s in stats
        ]
        return FacultyAnalyticsResponse(
            institution_avg_awarded_pct=benchmark,
            faculty=faculty,
        )

    # -----------------------------------------------------------------------
    # Batch Analytics
    # -----------------------------------------------------------------------

    @staticmethod
    async def batches(
        exam_paper_id: UUID | None,
        *,
        pass_pct: float = compute.DEFAULT_PASS_PCT,
        db: AsyncSession,
    ) -> BatchAnalyticsResponse:
        rows = await AnalyticsRepository.load_score_rows(exam_paper_id, db=db)
        stats = compute.compute_batch_stats(rows, pass_pct=pass_pct)
        batches = [
            BatchStatResponse(
                admission_year=s.admission_year,
                label=f"{s.admission_year} Batch" if s.admission_year else "Unknown batch",
                count=s.count,
                average=s.average,
                pass_pct=s.pass_pct,
                topper_pct=s.topper_pct,
                topper_user_id=s.topper_user_id,
            )
            for s in stats
        ]
        return BatchAnalyticsResponse(
            pass_threshold_pct=pass_pct,
            batches=batches,
        )

    # -----------------------------------------------------------------------
    # Grade Distribution
    # -----------------------------------------------------------------------

    @staticmethod
    async def grades(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> GradeAnalyticsResponse:
        rows = await AnalyticsRepository.load_score_rows(exam_paper_id, db=db)
        buckets = compute.compute_grade_distribution(rows)
        return GradeAnalyticsResponse(
            total_scripts=len(rows),
            buckets=[
                GradeBucketResponse(grade=b.grade, count=b.count, pct_of_total=b.pct_of_total)
                for b in buckets
            ],
        )

    # -----------------------------------------------------------------------
    # Revaluation Analytics
    # -----------------------------------------------------------------------

    @staticmethod
    async def revaluation(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> RevaluationAnalyticsResponse:
        rows = await AnalyticsRepository.load_reval_rows(exam_paper_id, db=db)
        s = compute.compute_revaluation_stats(rows)
        return RevaluationAnalyticsResponse(
            total_requests=s.total_requests,
            decided=s.decided,
            pending=s.total_requests - s.decided,
            marks_increased=s.marks_increased,
            marks_unchanged=s.marks_unchanged,
            average_increase=s.average_increase,
            max_increase=s.max_increase,
        )

    # -----------------------------------------------------------------------
    # Moderation Analytics
    # -----------------------------------------------------------------------

    @staticmethod
    async def moderation(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> ModerationAnalyticsResponse:
        rows = await AnalyticsRepository.load_mod_rows(exam_paper_id, db=db)
        s = compute.compute_moderation_stats(rows)
        return ModerationAnalyticsResponse(
            scripts_moderated=s.scripts_moderated,
            completed=s.completed,
            pending=s.pending,
            average_variance_pct=s.average_variance_pct,
            average_delta=s.average_delta,
        )

    # -----------------------------------------------------------------------
    # Dashboard bundle — single round-trip for a landing dashboard
    # -----------------------------------------------------------------------

    @staticmethod
    async def dashboard(
        exam_paper_id: UUID | None,
        *,
        pass_pct: float = compute.DEFAULT_PASS_PCT,
        top_n: int = 5,
        db: AsyncSession,
    ) -> DashboardResponse:
        # Load score rows ONCE and reuse for overview/grades/subjects.
        rows = await AnalyticsRepository.load_score_rows(exam_paper_id, db=db)

        overview_stats = compute.compute_overview(rows, pass_pct=pass_pct)
        grade_buckets = compute.compute_grade_distribution(rows)
        subject_stats = compute.compute_subject_stats(rows, pass_pct=pass_pct)

        paper_ids = {r.exam_paper_id for r in rows}
        title = None
        if exam_paper_id:
            labels = await AnalyticsRepository.load_paper_labels([str(exam_paper_id)], db=db)
            title = labels.get(str(exam_paper_id), {}).get("title")

        # Label only the top-N hardest subjects (compute already sorts asc by avg).
        top = subject_stats[:top_n]
        paper_labels = await AnalyticsRepository.load_paper_labels(
            [s.exam_paper_id for s in top], db=db
        )
        course_labels = await AnalyticsRepository.load_course_labels(
            [paper_labels.get(s.exam_paper_id, {}).get("course_id") for s in top], db=db
        )
        top_subjects = []
        for s in top:
            pl = paper_labels.get(s.exam_paper_id, {})
            cl = course_labels.get(pl.get("course_id") or "", {})
            top_subjects.append(SubjectStatResponse(
                exam_paper_id=s.exam_paper_id,
                exam_paper_title=pl.get("title"),
                course_code=cl.get("code"),
                course_title=cl.get("title"),
                count=s.count, average=s.average, median=s.median,
                highest=s.highest, lowest=s.lowest,
                pass_count=s.pass_count, fail_count=s.fail_count,
                pass_pct=s.pass_pct, fail_pct=s.fail_pct,
            ))

        reval = await ExamAnalyticsService.revaluation(exam_paper_id, db=db)
        mod = await ExamAnalyticsService.moderation(exam_paper_id, db=db)

        overview = OverviewResponse(
            scope="PAPER" if exam_paper_id else "INSTITUTION",
            exam_paper_id=str(exam_paper_id) if exam_paper_id else None,
            exam_paper_title=title,
            total_students=overview_stats.total_students,
            appeared=overview_stats.appeared,
            absent=overview_stats.absent,
            pass_count=overview_stats.pass_count,
            fail_count=overview_stats.fail_count,
            pass_pct=overview_stats.pass_pct,
            average_pct=overview_stats.average_pct,
            highest_pct=overview_stats.highest_pct,
            lowest_pct=overview_stats.lowest_pct,
            pass_threshold_pct=overview_stats.pass_threshold_pct,
            papers_count=len(paper_ids),
        )
        grades = GradeAnalyticsResponse(
            total_scripts=len(rows),
            buckets=[
                GradeBucketResponse(grade=b.grade, count=b.count, pct_of_total=b.pct_of_total)
                for b in grade_buckets
            ],
        )
        return DashboardResponse(
            overview=overview,
            grades=grades,
            top_subjects=top_subjects,
            revaluation=reval,
            moderation=mod,
        )
