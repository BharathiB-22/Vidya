"""
M09.8 Examination Analytics — data loaders.

Responsible ONLY for turning canonical exam tables into the normalised row
dataclasses consumed by analytics_compute.  No maths happens here; no maths
dependency leaks into the DB layer.

Tables read (all tenant-schema, scoped by the session search_path):
  exam_score_ledger          — finalised scores (ground truth)
  sis_student_profiles       — admission_year ("batch" dimension)
  scanned_scripts            — evaluator assignment + Gate-1 timestamps
  script_evaluations         — per-question marks (PRIMARY / MODERATION rounds)
  sis_revaluation_requests   — revaluation outcomes
  script_moderation_reviews  — moderation events
  exam_papers / courses      — subject labels (M08 / M01)
  users                      — evaluator display names

All loaders accept an optional `exam_paper_id` to scope to a single paper; when
None they aggregate across the whole tenant (institution-wide).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin.analytics_compute import (
    EvalRow,
    ModRow,
    RevalRow,
    ScoreRow,
)


def _paper_clause(column: str, exam_paper_id: UUID | None) -> str:
    return f" WHERE {column} = CAST(:pid AS uuid)" if exam_paper_id else ""


class AnalyticsRepository:

    # -----------------------------------------------------------------------
    # Finalised scores (overview / subject / batch / grade analytics)
    # -----------------------------------------------------------------------

    @staticmethod
    async def load_score_rows(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[ScoreRow]:
        sql = (
            "SELECT l.script_id, l.exam_paper_id, l.student_user_id, "
            "       l.total_marks, l.max_marks, l.has_board_adjustment, "
            "       sp.admission_year "
            "FROM exam_score_ledger l "
            "LEFT JOIN sis_student_profiles sp ON sp.user_id = l.student_user_id"
            + _paper_clause("l.exam_paper_id", exam_paper_id)
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        rows: list[ScoreRow] = []
        for r in result.mappings():
            rows.append(ScoreRow(
                script_id=str(r["script_id"]),
                exam_paper_id=str(r["exam_paper_id"]),
                student_user_id=str(r["student_user_id"]) if r["student_user_id"] else None,
                total_marks=float(r["total_marks"]),
                max_marks=float(r["max_marks"]),
                has_board_adjustment=bool(r["has_board_adjustment"]),
                admission_year=int(r["admission_year"]) if r["admission_year"] is not None else None,
            ))
        return rows

    # -----------------------------------------------------------------------
    # Faculty / evaluator workload
    # -----------------------------------------------------------------------

    @staticmethod
    async def load_eval_rows(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[EvalRow]:
        """
        One row per submitted script attributed to its primary evaluator.
        awarded_total = sum of final (or evaluator) marks for the PRIMARY round.
        turnaround = submitted_at - created_at, in hours.
        """
        where = (
            "WHERE s.evaluator_id IS NOT NULL AND s.submitted_at IS NOT NULL"
        )
        if exam_paper_id:
            where += " AND s.exam_paper_id = CAST(:pid AS uuid)"
        sql = (
            "SELECT s.id AS script_id, s.evaluator_id, "
            "       EXTRACT(EPOCH FROM (s.submitted_at - s.created_at)) / 3600.0 AS turnaround_hours, "
            "       COALESCE(SUM(COALESCE(e.final_marks, e.evaluator_marks)), 0) AS awarded_total, "
            "       COALESCE(SUM(e.max_marks), 0) AS max_marks "
            "FROM scanned_scripts s "
            "JOIN script_evaluations e "
            "  ON e.script_id = s.id AND e.evaluation_round = 'PRIMARY' "
            f"{where} "
            "GROUP BY s.id, s.evaluator_id, s.submitted_at, s.created_at"
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        rows: list[EvalRow] = []
        for r in result.mappings():
            th = r["turnaround_hours"]
            rows.append(EvalRow(
                script_id=str(r["script_id"]),
                evaluator_id=str(r["evaluator_id"]),
                awarded_total=float(r["awarded_total"]),
                max_marks=float(r["max_marks"]),
                turnaround_hours=round(float(th), 2) if th is not None else None,
            ))
        return rows

    # -----------------------------------------------------------------------
    # Revaluation outcomes
    # -----------------------------------------------------------------------

    @staticmethod
    async def load_reval_rows(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[RevalRow]:
        sql = (
            "SELECT id, status, original_total, awarded_total "
            "FROM sis_revaluation_requests"
            + _paper_clause("exam_paper_id", exam_paper_id)
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        rows: list[RevalRow] = []
        for r in result.mappings():
            rows.append(RevalRow(
                request_id=str(r["id"]),
                status=str(r["status"]),
                original_total=float(r["original_total"]),
                awarded_total=float(r["awarded_total"]) if r["awarded_total"] is not None else None,
            ))
        return rows

    # -----------------------------------------------------------------------
    # Moderation events
    # -----------------------------------------------------------------------

    @staticmethod
    async def load_mod_rows(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[ModRow]:
        where = _paper_clause("m.exam_paper_id", exam_paper_id)
        sql = (
            "SELECT m.id, m.status, m.primary_total, m.secondary_total, m.variance_pct, "
            "       mod_e.moderated_total "
            "FROM script_moderation_reviews m "
            "LEFT JOIN ( "
            "   SELECT script_id, SUM(COALESCE(final_marks, evaluator_marks)) AS moderated_total "
            "   FROM script_evaluations WHERE evaluation_round = 'MODERATION' "
            "   GROUP BY script_id "
            ") mod_e ON mod_e.script_id = m.script_id"
            + where
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        rows: list[ModRow] = []
        for r in result.mappings():
            mt = r["moderated_total"]
            rows.append(ModRow(
                review_id=str(r["id"]),
                status=str(r["status"]),
                primary_total=float(r["primary_total"]),
                secondary_total=float(r["secondary_total"]),
                variance_pct=float(r["variance_pct"]),
                moderated_total=float(mt) if mt is not None else None,
            ))
        return rows

    # -----------------------------------------------------------------------
    # Label lookups
    # -----------------------------------------------------------------------

    @staticmethod
    async def load_paper_labels(
        paper_ids: list[str],
        *,
        db: AsyncSession,
    ) -> dict[str, dict]:
        """{exam_paper_id: {title, course_id, total_marks}} for the given papers."""
        if not paper_ids:
            return {}
        sql = (
            "SELECT id, title, course_id, total_marks "
            "FROM exam_papers WHERE id = ANY(CAST(:ids AS uuid[]))"
        )
        result = await db.execute(text(sql), {"ids": paper_ids})
        out: dict[str, dict] = {}
        for r in result.mappings():
            out[str(r["id"])] = {
                "title": r["title"],
                "course_id": str(r["course_id"]) if r["course_id"] else None,
                "total_marks": float(r["total_marks"]) if r["total_marks"] is not None else None,
            }
        return out

    @staticmethod
    async def load_course_labels(
        course_ids: list[str],
        *,
        db: AsyncSession,
    ) -> dict[str, dict]:
        """{course_id: {code, title}} for the given courses (M01)."""
        ids = [c for c in course_ids if c]
        if not ids:
            return {}
        sql = "SELECT id, code, title FROM courses WHERE id = ANY(CAST(:ids AS uuid[]))"
        result = await db.execute(text(sql), {"ids": ids})
        return {
            str(r["id"]): {"code": r["code"], "title": r["title"]}
            for r in result.mappings()
        }

    @staticmethod
    async def load_user_names(
        user_ids: list[str],
        *,
        db: AsyncSession,
    ) -> dict[str, str]:
        """{user_id: full_name} for evaluator labelling."""
        ids = [u for u in user_ids if u]
        if not ids:
            return {}
        sql = "SELECT id, full_name FROM users WHERE id = ANY(CAST(:ids AS uuid[]))"
        result = await db.execute(text(sql), {"ids": ids})
        return {str(r["id"]): r["full_name"] for r in result.mappings()}
