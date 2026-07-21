"""
M06 Moderation Report Export — CSV report for faculty.

Generates a per-assignment moderation report:
  Columns: student_user_id, submitted_at, is_late, ai_scan_status,
           plagiarism_score, overall_ai_score, overall_human_score,
           delta (human - ai), confidence_level, status, ratified_at,
           final_score, per_criterion_[id]_ai, per_criterion_[id]_human

Result is returned as a CSV string. The caller (Celery task or endpoint)
is responsible for uploading to S3 and returning a presigned URL.
"""
from __future__ import annotations

import csv
import io
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m06_labs_evaluator.repository import (
    SubmissionRepository,
)

logger = logging.getLogger("vidya.m06.report_export")


async def generate_csv_report(
    assignment_id: UUID,
    rubric: list[dict],
    *,
    db: AsyncSession,
) -> str:
    """
    Generate a moderation report CSV for all submissions in `assignment_id`.

    rubric: list of criterion dicts (from LabAssignment.rubric)
    Returns CSV string (UTF-8).
    """
    submissions, _ = await SubmissionRepository.list_for_assignment(
        assignment_id, db=db, limit=1000
    )

    # Per-criterion column headers
    criterion_ids = [c.get("criterion_id", f"c{i}") for i, c in enumerate(rubric)]

    base_headers = [
        "submission_id",
        "student_user_id",
        "submitted_at",
        "is_late",
        "ai_scan_status",
        "ai_scan_probability",
        "plagiarism_score",
        "overall_ai_score",
        "overall_human_score",
        "delta",
        "confidence_level",
        "status",
        "ratified_at",
        "final_score",
    ]
    criterion_ai_headers    = [f"criterion_{cid}_ai_score"    for cid in criterion_ids]
    criterion_human_headers = [f"criterion_{cid}_human_score" for cid in criterion_ids]
    headers = base_headers + criterion_ai_headers + criterion_human_headers

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()

    for sub in submissions:
        row: dict = {
            "submission_id":    str(sub.id),
            "student_user_id":  str(sub.student_user_id),
            "submitted_at":     sub.submitted_at.isoformat() if sub.submitted_at else "",
            "is_late":          sub.is_late,
            "ai_scan_status":   sub.ai_scan_status.value if sub.ai_scan_status else "",
            "ai_scan_probability": (
                sub.ai_scan_result.get("probability", "") if sub.ai_scan_result else ""
            ),
            "status": sub.status.value if sub.status else "",
        }

        eval_obj = sub.evaluation
        if eval_obj:
            ai_score    = float(eval_obj.overall_ai_score or 0)
            human_score = float(eval_obj.overall_human_score) if eval_obj.overall_human_score is not None else None
            row["plagiarism_score"]     = eval_obj.plagiarism_score or ""
            row["overall_ai_score"]     = ai_score
            row["overall_human_score"]  = human_score if human_score is not None else ""
            row["delta"]                = round(human_score - ai_score, 2) if human_score is not None else ""
            row["confidence_level"]     = eval_obj.confidence_level.value if eval_obj.confidence_level else ""

            # Per-criterion scores
            rubric_map: dict[str, dict] = {
                r.get("criterion_id", ""): r for r in (eval_obj.rubric_scores or [])
            }
            for cid in criterion_ids:
                cr = rubric_map.get(cid, {})
                row[f"criterion_{cid}_ai_score"]    = cr.get("ai_score", "")
                row[f"criterion_{cid}_human_score"] = cr.get("human_score", "")
        else:
            row["plagiarism_score"] = ""
            row["overall_ai_score"] = ""
            row["overall_human_score"] = ""
            row["delta"] = ""
            row["confidence_level"] = ""
            for cid in criterion_ids:
                row[f"criterion_{cid}_ai_score"]    = ""
                row[f"criterion_{cid}_human_score"] = ""

        # Grade ledger (ratified entry)
        grade = sub.grade_entry
        if grade:
            row["ratified_at"] = grade.ratified_at.isoformat() if grade.ratified_at else ""
            row["final_score"] = float(grade.final_score)
        else:
            row["ratified_at"] = ""
            row["final_score"] = ""

        writer.writerow(row)

    return output.getvalue()
