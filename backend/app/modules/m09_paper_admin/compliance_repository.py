"""
M09.9 Compliance & Audit — data loaders.

Reads two kinds of sources and shapes them into plain dict rows for the pure
``compliance_core`` layer:

  1. ``public.audit_logs``  — the canonical append-only event stream.  Always
     filtered by ``tenant_id`` (the column scoping in the global table) AND by
     the curated examination event-type set, so no cross-tenant leakage and no
     non-exam noise reaches compliance views.

  2. Tenant-schema exam tables — exam_mark_audit, scanned_scripts,
     script_evaluations, script_moderation_reviews, sis_revaluation_requests,
     exam_board_sessions / approvals, exam_papers, users — for mark lineage and
     the compliance reports.  These resolve via the session search_path.

No maths and no policy here; only retrieval.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin.compliance_core import EXAM_EVENT_TYPES


class ComplianceRepository:

    # =======================================================================
    # Audit event stream (public.audit_logs)
    # =======================================================================

    @staticmethod
    async def query_events(
        *,
        tenant_id: UUID,
        event_types: list[str] | None = None,
        actor_user_id: UUID | None = None,
        target_ids: list[str] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[dict], int]:
        """Return (rows, total) of examination audit events for one tenant.

        ``event_types`` defaults to the full curated exam set.  ``target_ids``
        scopes to specific entities (e.g. a student's scripts).
        """
        types = event_types if event_types is not None else list(EXAM_EVENT_TYPES)
        clauses = ["tenant_id = CAST(:tenant_id AS uuid)", "event_type = ANY(:types)"]
        params: dict = {"tenant_id": str(tenant_id), "types": types}

        if actor_user_id is not None:
            clauses.append("actor_user_id = CAST(:actor AS uuid)")
            params["actor"] = str(actor_user_id)
        if target_ids is not None:
            # Empty target set ⇒ no rows (avoid a SQL `= ANY('{}')` that matches nothing oddly)
            if not target_ids:
                return [], 0
            clauses.append("target_id = ANY(:target_ids)")
            params["target_ids"] = target_ids
        if date_from is not None:
            clauses.append("created_at >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            clauses.append("created_at <= :date_to")
            params["date_to"] = date_to

        where = " AND ".join(clauses)

        total_sql = f"SELECT COUNT(*) FROM public.audit_logs WHERE {where}"
        total = (await db.execute(text(total_sql), params)).scalar_one()

        rows_sql = (
            "SELECT id, event_type, actor_user_id, actor_role, target_entity, "
            "       target_id, metadata, created_at "
            f"FROM public.audit_logs WHERE {where} "
            "ORDER BY created_at DESC OFFSET :offset LIMIT :limit"
        )
        params_rows = {**params, "offset": offset, "limit": limit}
        result = await db.execute(text(rows_sql), params_rows)
        rows = [dict(r) for r in result.mappings()]
        return rows, total

    @staticmethod
    async def count_events_by_type(
        *,
        tenant_id: UUID,
        exam_paper_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        db: AsyncSession,
    ) -> dict[str, int]:
        """GROUP BY event_type over the exam event stream (for dashboard KPIs).

        When ``exam_paper_id`` is given, scope to the scripts of that paper via
        target_id; paper-less aggregation covers the whole tenant.
        """
        clauses = ["tenant_id = CAST(:tenant_id AS uuid)", "event_type = ANY(:types)"]
        params: dict = {"tenant_id": str(tenant_id), "types": list(EXAM_EVENT_TYPES)}

        if exam_paper_id is not None:
            clauses.append(
                "target_id IN (SELECT CAST(id AS text) FROM scanned_scripts "
                "WHERE exam_paper_id = CAST(:pid AS uuid))"
            )
            params["pid"] = str(exam_paper_id)
        if date_from is not None:
            clauses.append("created_at >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            clauses.append("created_at <= :date_to")
            params["date_to"] = date_to

        where = " AND ".join(clauses)
        sql = (
            "SELECT event_type, COUNT(*) AS n "
            f"FROM public.audit_logs WHERE {where} GROUP BY event_type"
        )
        result = await db.execute(text(sql), params)
        return {r["event_type"]: int(r["n"]) for r in result.mappings()}

    # =======================================================================
    # Resolving scope helpers
    # =======================================================================

    @staticmethod
    async def script_ids_for_student(student_user_id: UUID, *, db: AsyncSession) -> list[str]:
        """All script ids belonging to a student (used for the student audit trail)."""
        sql = "SELECT CAST(id AS text) AS id FROM scanned_scripts WHERE student_user_id = CAST(:sid AS uuid)"
        result = await db.execute(text(sql), {"sid": str(student_user_id)})
        return [r["id"] for r in result.mappings()]

    @staticmethod
    async def script_ids_for_exam(exam_paper_id: UUID, *, db: AsyncSession) -> list[str]:
        sql = "SELECT CAST(id AS text) AS id FROM scanned_scripts WHERE exam_paper_id = CAST(:pid AS uuid)"
        result = await db.execute(text(sql), {"pid": str(exam_paper_id)})
        return [r["id"] for r in result.mappings()]

    # =======================================================================
    # Mark-change history
    # =======================================================================

    @staticmethod
    async def mark_audit_for_script(script_id: UUID, *, db: AsyncSession) -> list[dict]:
        sql = (
            "SELECT id, script_id, exam_paper_id, question_id, evaluation_round, "
            "       student_user_id, masked_id, change_type, previous_marks, new_marks, "
            "       max_marks, delta, actor_user_id, actor_role, reason, source_event, created_at "
            "FROM exam_mark_audit WHERE script_id = CAST(:sid AS uuid) "
            "ORDER BY created_at ASC"
        )
        result = await db.execute(text(sql), {"sid": str(script_id)})
        return [dict(r) for r in result.mappings()]

    @staticmethod
    async def evaluations_for_script(script_id: UUID, *, db: AsyncSession) -> list[dict]:
        sql = (
            "SELECT question_id, question_type, evaluation_round, max_marks, "
            "       ai_suggested_marks, ai_justification, evaluator_marks, evaluator_note, "
            "       board_adjusted_marks, board_adjustment_note, final_marks "
            "FROM script_evaluations WHERE script_id = CAST(:sid AS uuid)"
        )
        result = await db.execute(text(sql), {"sid": str(script_id)})
        return [dict(r) for r in result.mappings()]

    @staticmethod
    async def script_header(script_id: UUID, *, db: AsyncSession) -> dict | None:
        sql = (
            "SELECT CAST(id AS text) AS id, CAST(exam_paper_id AS text) AS exam_paper_id, "
            "       masked_id, status, CAST(student_user_id AS text) AS student_user_id "
            "FROM scanned_scripts WHERE id = CAST(:sid AS uuid)"
        )
        result = await db.execute(text(sql), {"sid": str(script_id)})
        row = result.mappings().first()
        return dict(row) if row else None

    # =======================================================================
    # Compliance reports
    # =======================================================================

    @staticmethod
    async def board_sessions(exam_paper_id: UUID | None, *, db: AsyncSession) -> list[dict]:
        where = " WHERE s.exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        sql = (
            "SELECT CAST(s.id AS text) AS session_id, CAST(s.exam_paper_id AS text) AS exam_paper_id, "
            "       s.session_title, s.status, "
            "       CAST(s.convened_by AS text) AS convened_by, s.convened_at, "
            "       CAST(s.decided_by AS text) AS decided_by, s.decided_at, "
            "       CAST(s.declared_by AS text) AS declared_by, s.declared_at, "
            "       s.board_remarks, "
            "       a.mean_marks, a.pass_rate_pct, a.total_scripts "
            "FROM exam_board_sessions s "
            "LEFT JOIN exam_board_course_approvals a ON a.session_id = s.id "
            f"{where} ORDER BY s.convened_at DESC"
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        return [dict(r) for r in result.mappings()]

    @staticmethod
    async def moderation_reviews(exam_paper_id: UUID | None, *, db: AsyncSession) -> list[dict]:
        where = " WHERE m.exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        sql = (
            "SELECT CAST(m.id AS text) AS review_id, CAST(m.script_id AS text) AS script_id, "
            "       sc.masked_id, CAST(m.exam_paper_id AS text) AS exam_paper_id, "
            "       m.primary_total, m.secondary_total, m.variance_pct, m.variance_threshold, "
            "       m.flag_reason, CAST(m.flagged_by AS text) AS flagged_by, m.flagged_at, "
            "       CAST(m.moderator_id AS text) AS moderator_id, m.moderation_notes, "
            "       m.status, m.completed_at "
            "FROM script_moderation_reviews m "
            "LEFT JOIN scanned_scripts sc ON sc.id = m.script_id "
            f"{where} ORDER BY m.flagged_at DESC"
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        return [dict(r) for r in result.mappings()]

    @staticmethod
    async def revaluation_requests(exam_paper_id: UUID | None, *, db: AsyncSession) -> list[dict]:
        where = " WHERE exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        sql = (
            "SELECT CAST(id AS text) AS request_id, CAST(script_id AS text) AS script_id, "
            "       CAST(exam_paper_id AS text) AS exam_paper_id, status, "
            "       original_total, revaluation_total, awarded_total, "
            "       CAST(assigned_evaluator_id AS text) AS assigned_evaluator_id, "
            "       CAST(decided_by AS text) AS decided_by, decided_at, "
            "       reason, board_remarks, created_at "
            "FROM sis_revaluation_requests "
            f"{where} ORDER BY created_at DESC"
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        return [dict(r) for r in result.mappings()]

    @staticmethod
    async def evaluator_activity(exam_paper_id: UUID | None, *, db: AsyncSession) -> list[dict]:
        """Per-evaluator assignment + submission + mark-change activity."""
        paper = " AND s.exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        sql = (
            "SELECT CAST(s.evaluator_id AS text) AS evaluator_id, "
            "       COUNT(*) AS scripts_assigned, "
            "       COUNT(*) FILTER (WHERE s.submitted_at IS NOT NULL) AS scripts_submitted, "
            "       MAX(GREATEST(COALESCE(s.submitted_at, s.created_at), s.created_at)) AS last_activity_at "
            "FROM scanned_scripts s "
            f"WHERE s.evaluator_id IS NOT NULL{paper} "
            "GROUP BY s.evaluator_id"
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        return [dict(r) for r in result.mappings()]

    @staticmethod
    async def mark_change_counts_by_actor(
        exam_paper_id: UUID | None, *, db: AsyncSession
    ) -> dict[str, int]:
        """Per-actor count of recorded field-level mark changes (exam_mark_audit)."""
        where = " WHERE exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        sql = (
            "SELECT CAST(actor_user_id AS text) AS actor, COUNT(*) AS n "
            f"FROM exam_mark_audit{where} GROUP BY actor_user_id"
        )
        params = {"pid": str(exam_paper_id)} if exam_paper_id else {}
        result = await db.execute(text(sql), params)
        return {r["actor"]: int(r["n"]) for r in result.mappings()}

    # =======================================================================
    # Label lookups
    # =======================================================================

    @staticmethod
    async def user_names(user_ids: list[str], *, db: AsyncSession) -> dict[str, str]:
        ids = [u for u in {x for x in user_ids if x}]
        if not ids:
            return {}
        sql = "SELECT CAST(id AS text) AS id, full_name FROM users WHERE id = ANY(CAST(:ids AS uuid[]))"
        result = await db.execute(text(sql), {"ids": ids})
        return {r["id"]: r["full_name"] for r in result.mappings()}

    @staticmethod
    async def paper_titles(paper_ids: list[str], *, db: AsyncSession) -> dict[str, str]:
        ids = [p for p in {x for x in paper_ids if x}]
        if not ids:
            return {}
        sql = "SELECT CAST(id AS text) AS id, title FROM exam_papers WHERE id = ANY(CAST(:ids AS uuid[]))"
        result = await db.execute(text(sql), {"ids": ids})
        return {r["id"]: r["title"] for r in result.mappings()}

    # =======================================================================
    # Append-only writer (the ONLY write path in this subsystem)
    # =======================================================================

    @staticmethod
    async def insert_mark_audit(rows: list[dict], *, db: AsyncSession) -> None:
        """Bulk-insert append-only mark audit rows.  No UPDATE/DELETE exists."""
        if not rows:
            return
        sql = (
            "INSERT INTO exam_mark_audit "
            "(script_id, exam_paper_id, question_id, evaluation_round, student_user_id, "
            " masked_id, change_type, previous_marks, new_marks, max_marks, delta, "
            " actor_user_id, actor_role, reason, source_event) VALUES "
            "(CAST(:script_id AS uuid), CAST(:exam_paper_id AS uuid), "
            " CAST(:question_id AS uuid), :evaluation_round, CAST(:student_user_id AS uuid), "
            " :masked_id, :change_type, :previous_marks, :new_marks, :max_marks, :delta, "
            " CAST(:actor_user_id AS uuid), :actor_role, :reason, :source_event)"
        )
        await db.execute(text(sql), rows)
