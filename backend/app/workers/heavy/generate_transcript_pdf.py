"""
H61 – Generate Transcript PDF (Celery heavy task).

Flow:
  1. Load all LOCKED semester + subject results for the student.
  2. Apply best-attempt selection per course (supplementary / improvement).
  3. Build snapshot rows in sis_transcript_semester_lines / sis_transcript_subject_lines.
  4. Freeze header fields on sis_transcripts (number, verification_code, CGPA …).
  5. Render PDF via ReportLab (QR code embedded via reportlab.graphics.barcode.qr).
  6. Upload PDF to S3/MinIO.
  7. Upsert public.public_transcript_index.
  8. Update transcript.status → GENERATED.

Non-negotiable invariants:
  - Only LOCKED result declarations are included.
  - Best-attempt selection: for each course, pick the result from the declaration
    with the latest attempt_number where result_status = PASS; if none passed,
    pick latest FAIL attempt.
  - All mutations are in a single SQLAlchemy session committed atomically.
  - Verification code is a new UUID4 generated here (not pre-assigned).
  - PDF includes: Internal Marks, External Marks, Total Marks, Grade (per approval #3).
  - No autonomous degree conferral. Degree status is advisory only.
"""
from __future__ import annotations

import asyncio
import io
import logging
import sys
import uuid as _uuid_module
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.database import tenant_schema_scope
from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.h61.transcript")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        # Re-apply the schema at the START OF EVERY TRANSACTION, not once per
        # session. A commit hands this connection back — NullPool closes it, a pool
        # recycles it — so anything after the first commit would otherwise run with
        # search_path = public, and a pooled connection could arrive still carrying
        # ANOTHER tenant's search_path. A commit cannot undo a per-BEGIN SET LOCAL.
        from app.database import bind_tenant_search_path
        bind_tenant_search_path(_async_engine)
    return _async_engine


# ─────────────────────────────────────────────────────────────────────────────
# Celery task entry point
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.generate_transcript_pdf",
    autoretry_for=(),
    max_retries=0,
)
def generate_transcript_pdf(
    *,
    transcript_id: str,
    tenant_id: str,
    schema_name: str,
    actor_user_id: str,
    actor_role: str,
    tenant_code: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Which tenant every transaction in this task belongs to. Held for the whole
    # run and dropped at the end of it: a worker process is long-lived and serves
    # every tenant in turn, and a schema left set is one the next task inherits.
    with tenant_schema_scope(schema_name):
        return asyncio.run(
            _run(
                transcript_id = UUID(transcript_id),
                tenant_id     = UUID(tenant_id),
                schema_name   = schema_name,
                actor_user_id = UUID(actor_user_id),
                actor_role    = actor_role,
                tenant_code   = tenant_code,
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# Inner async implementation
# ─────────────────────────────────────────────────────────────────────────────

async def _run(
    transcript_id: UUID,
    tenant_id: UUID,
    schema_name: str,
    actor_user_id: UUID,
    actor_role: str,
    tenant_code: str,
) -> dict:
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.m11_sis.results_models import (
        DeclarationStatus,
        SisResultDeclaration,
        SisSemesterResult,
        SisSubjectResult,
    )
    from app.modules.m11_sis.transcript_models import (
        SisTranscriptSemesterLine,
        SisTranscriptSubjectLine,
        TranscriptStatus,
    )
    from app.modules.m11_sis.transcript_repository import (
        TranscriptLinesRepo,
        TranscriptRepo,
    )

    now = datetime.now(timezone.utc)
    engine = _get_async_engine()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        # ── 1. Load transcript ──────────────────────────────────────────────
        transcript = await TranscriptRepo.get_by_id(transcript_id, session)
        if not transcript:
            raise ValueError(f"Transcript {transcript_id} not found.")
        if transcript.status not in (TranscriptStatus.REQUESTED, TranscriptStatus.STALE):
            raise ValueError(
                f"Transcript {transcript_id} is in status '{transcript.status}'; "
                "expected REQUESTED or STALE."
            )

        student_id = transcript.student_id

        # ── 2. Load student USN / profile ───────────────────────────────────
        from app.modules.m11_sis.models import SisStudentProfile
        profile = (await session.execute(
            select(SisStudentProfile).where(SisStudentProfile.user_id == student_id)
        )).scalar_one_or_none()
        usn = profile.usn if profile else None

        # ── 3. Load tenant branding ─────────────────────────────────────────
        t_row = (await session.execute(
            text("SELECT name, logo_url FROM public.tenants WHERE id = :tid"),
            {"tid": str(tenant_id)},
        )).mappings().one_or_none()
        institution_name = t_row["name"]     if t_row else "Institution"
        institution_logo = t_row["logo_url"] if t_row else None

        # ── 4. Load enrollment → program / batch / dept / school ────────────
        program_name   = None
        department_name = None
        school_name    = None
        batch_name     = None
        degree_title   = None
        program_obj    = None
        min_credits    = None

        from app.modules.m_academics.models import (
            AcadBatch, AcadEnrollment, AcadProgram, AcadSection, AcadSemester,
        )
        enrollment = (await session.execute(
            select(AcadEnrollment).where(
                AcadEnrollment.student_id == student_id,
                AcadEnrollment.is_active.is_(True),
            ).limit(1)
        )).scalar_one_or_none()

        if enrollment:
            section = await session.get(AcadSection, enrollment.section_id)
            if section:
                sem = await session.get(AcadSemester, section.semester_id)
                if sem:
                    batch_obj = await session.get(AcadBatch, sem.batch_id)
                    if batch_obj:
                        batch_name = batch_obj.name
                        program_obj = await session.get(AcadProgram, batch_obj.program_id)
                        if program_obj:
                            program_name = program_obj.name
                            degree_title = getattr(program_obj, "degree_title", None)
                            min_credits  = getattr(program_obj, "min_credits_for_degree", None)
                        # Department / school via school FK on AcadProgram
                        if program_obj and getattr(program_obj, "school_id", None):
                            from app.modules.m_academics.models import AcadSchool
                            school_obj = await session.get(AcadSchool, program_obj.school_id)
                            if school_obj:
                                school_name = school_obj.name

        # ── 5. Load all LOCKED semester results ─────────────────────────────
        sr_rows = list((await session.execute(
            select(SisSemesterResult)
            .where(SisSemesterResult.student_id == student_id)
            .order_by(SisSemesterResult.computed_at)
        )).scalars().all())

        # Filter to LOCKED declarations only
        locked_decl_ids: set[UUID] = set()
        decl_cache: dict[UUID, SisResultDeclaration] = {}
        for sr in sr_rows:
            if sr.declaration_id not in decl_cache:
                decl = await session.get(SisResultDeclaration, sr.declaration_id)
                decl_cache[sr.declaration_id] = decl
            decl = decl_cache[sr.declaration_id]
            if decl and decl.status == DeclarationStatus.LOCKED.value:
                locked_decl_ids.add(sr.declaration_id)

        valid_srs = [sr for sr in sr_rows if sr.declaration_id in locked_decl_ids]
        if not valid_srs:
            raise ValueError(
                f"No LOCKED semester results found for student {student_id}. "
                "Lock result declarations before generating transcript."
            )

        # ── 6. Load subject results per semester; apply best-attempt ─────────
        semester_lines: list[SisTranscriptSemesterLine] = []
        all_subject_lines: list[SisTranscriptSubjectLine] = []

        total_credits_attempted = Decimal("0")
        total_credits_earned    = Decimal("0")
        arrear_count            = 0
        final_cgpa: Optional[Decimal] = None

        for disp_idx, sr in enumerate(sorted(valid_srs, key=lambda x: x.computed_at)):
            decl = decl_cache.get(sr.declaration_id)
            sem_line = SisTranscriptSemesterLine(
                id                             = _uuid_module.uuid4(),
                transcript_id                  = transcript_id,
                semester_id                    = sr.semester_id,
                declaration_id                 = sr.declaration_id,
                semester_number_snapshot       = None,  # enriched below
                semester_name_snapshot         = decl.snapshot_semester_name if decl else None,
                academic_year_snapshot         = decl.snapshot_academic_year if decl else None,
                sgpa_snapshot                  = sr.sgpa,
                cgpa_snapshot                  = sr.cgpa,
                credits_attempted_snapshot     = sr.total_credits_attempted,
                credits_earned_snapshot        = sr.total_credits_earned,
                overall_result_status_snapshot = sr.overall_result_status,
                display_order                  = disp_idx + 1,
            )
            # Enrich semester number from AcadSemester if available
            if sr.semester_id:
                acad_sem = await session.get(AcadSemester, sr.semester_id)
                if acad_sem:
                    sem_line.semester_number_snapshot = acad_sem.semester_number

            semester_lines.append(sem_line)

            if sr.total_credits_attempted:
                total_credits_attempted += Decimal(str(sr.total_credits_attempted))
            if sr.total_credits_earned:
                total_credits_earned += Decimal(str(sr.total_credits_earned))
            if sr.cgpa is not None:
                final_cgpa = Decimal(str(sr.cgpa))

            # Load subject results for this declaration
            subj_rows = list((await session.execute(
                select(SisSubjectResult)
                .where(
                    SisSubjectResult.student_id   == student_id,
                    SisSubjectResult.declaration_id == sr.declaration_id,
                )
                .order_by(SisSubjectResult.attempt_number)
            )).scalars().all())

            # Group by course_id to apply best-attempt logic
            by_course: dict[UUID, list[SisSubjectResult]] = defaultdict(list)
            for s in subj_rows:
                by_course[s.course_id].append(s)

            subj_lines: list[SisTranscriptSubjectLine] = []
            subj_disp = 0
            for cid, attempts in by_course.items():
                sorted_attempts = sorted(attempts, key=lambda a: a.attempt_number)
                # Best = last PASS; fallback = latest attempt
                best = next(
                    (a for a in reversed(sorted_attempts) if a.result_status == "PASS"),
                    sorted_attempts[-1],
                )
                if best.result_status != "PASS":
                    arrear_count += 1

                # Load course metadata
                from app.modules.m01_program_advisor.models import Course as AcadCourse
                course_obj = await session.get(AcadCourse, cid)

                for attempt in sorted_attempts:
                    subj_disp += 1
                    is_best = (attempt.id == best.id)
                    max_marks = None
                    pct = None
                    if attempt.total_marks is not None and attempt.total_marks > 0:
                        # max marks not stored on subject result; derive from grading policy
                        pass

                    sl = SisTranscriptSubjectLine(
                        id                      = _uuid_module.uuid4(),
                        transcript_id           = transcript_id,
                        semester_line_id        = sem_line.id,
                        course_id               = cid,
                        course_code_snapshot    = course_obj.code  if course_obj else None,
                        course_name_snapshot    = course_obj.title if course_obj else None,
                        course_credits_snapshot = course_obj.credits if course_obj else None,
                        internal_marks_snapshot = attempt.internal_marks,
                        external_marks_snapshot = attempt.external_marks,
                        grace_marks_snapshot    = attempt.grace_marks,
                        total_marks_snapshot    = attempt.total_marks,
                        max_marks_snapshot      = max_marks,
                        percentage_snapshot     = pct,
                        grade_letter_snapshot   = attempt.grade_letter,
                        grade_point_snapshot    = attempt.grade_point,
                        is_pass_snapshot        = (attempt.result_status == "PASS"),
                        result_status_snapshot  = attempt.result_status,
                        attempt_number          = attempt.attempt_number,
                        declaration_type_snapshot = decl.declaration_type if decl else None,
                        is_best_attempt         = is_best,
                        display_order           = subj_disp,
                    )
                    subj_lines.append(sl)

            all_subject_lines.extend(subj_lines)

        # ── 7. Compute degree status (advisory only) ──────────────────────
        from app.modules.m11_sis.transcript_models import DegreeStatus
        any_withheld = any(
            sr.overall_result_status in ("WITHHELD", "FAIL") for sr in valid_srs
        )
        credits_ok = (
            min_credits and total_credits_earned >= Decimal(str(min_credits))
        ) if min_credits else True

        if any_withheld or arrear_count > 0 or not credits_ok:
            degree_status = DegreeStatus.NOT_ELIGIBLE
        else:
            degree_status = DegreeStatus.ELIGIBLE

        # ── 8. Assign transcript number and verification code ─────────────
        year = now.year
        transcript_number = await TranscriptRepo.next_transcript_number(
            tenant_code, year, session
        )
        verification_code = _uuid_module.uuid4()

        # ── 9. Freeze snapshot on SisTranscript ───────────────────────────
        transcript.transcript_number              = transcript_number
        transcript.verification_code              = verification_code
        transcript.usn_snapshot                   = usn
        transcript.program_name_snapshot          = program_name
        transcript.department_name_snapshot       = department_name
        transcript.school_name_snapshot           = school_name
        transcript.batch_name_snapshot            = batch_name
        transcript.degree_title_snapshot          = degree_title
        transcript.overall_cgpa_snapshot          = final_cgpa
        transcript.total_credits_attempted_snapshot = total_credits_attempted
        transcript.total_credits_earned_snapshot  = total_credits_earned
        transcript.arrear_count_snapshot          = arrear_count
        transcript.degree_status_snapshot         = degree_status.value
        transcript.semesters_included             = len(semester_lines)
        transcript.generated_by                   = actor_user_id
        transcript.generated_at                   = now
        transcript.updated_at                     = now
        await session.flush()

        # ── 10. Persist snapshot lines ────────────────────────────────────
        await TranscriptLinesRepo.bulk_insert_semester_lines(semester_lines, session)
        for sem_line in semester_lines:
            subj_for_sem = [
                sl for sl in all_subject_lines if sl.semester_line_id == sem_line.id
            ]
            if subj_for_sem:
                await TranscriptLinesRepo.bulk_insert_subject_lines(subj_for_sem, session)

        # ── 11. Generate PDF ──────────────────────────────────────────────
        pdf_context = {
            "transcript_number":  transcript_number,
            "verification_code":  str(verification_code),
            "student_name":       transcript.student_name_snapshot,
            "usn":                usn,
            "program_name":       program_name,
            "degree_title":       degree_title,
            "school_name":        school_name,
            "batch_name":         batch_name,
            "institution_name":   institution_name,
            "institution_logo":   institution_logo,
            "transcript_type":    transcript.transcript_type,
            "issued_at":          None,     # not yet issued
            "overall_cgpa":       str(final_cgpa) if final_cgpa else "—",
            "total_credits_earned": str(total_credits_earned),
            "arrear_count":       arrear_count,
            "degree_status":      degree_status.value,
            "semesters":          _build_pdf_semesters(semester_lines, all_subject_lines),
        }
        pdf_bytes = _render_pdf(pdf_context)

        # ── 12. Upload to S3 ──────────────────────────────────────────────
        s3_key = await asyncio.to_thread(
            _s3_put_object,
            pdf_bytes,
            f"transcripts/{schema_name}/{transcript_id}.pdf",
        )

        # ── 13. Update transcript with PDF info + status ──────────────────
        transcript.pdf_s3_key       = s3_key
        transcript.pdf_generated_at = now
        transcript.status           = TranscriptStatus.GENERATED
        transcript.updated_at       = now
        await session.flush()

        # ── 14. Upsert public index (not yet issued; status = GENERATED) ──
        # We do NOT write to public index here — only ISSUED transcripts appear.
        # The issue() service call handles that.

        await session.commit()

        logger.info(
            "Transcript PDF generated: %s → %s (arrears=%d cgpa=%s)",
            transcript_id, transcript_number, arrear_count, final_cgpa,
        )
        return {
            "transcript_id":    str(transcript_id),
            "transcript_number": transcript_number,
            "s3_key":            s3_key,
            "arrear_count":      arrear_count,
            "degree_status":     degree_status.value,
            "semesters_included": len(semester_lines),
        }


# ─────────────────────────────────────────────────────────────────────────────
# PDF helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_pdf_semesters(
    semester_lines: list,
    subject_lines: list,
) -> list[dict]:
    out = []
    for sl in sorted(semester_lines, key=lambda x: x.display_order):
        subjects = [
            s for s in subject_lines
            if s.semester_line_id == sl.id and s.is_best_attempt
        ]
        subjects_sorted = sorted(subjects, key=lambda x: x.display_order)
        out.append({
            "semester_number": sl.semester_number_snapshot,
            "semester_name":   sl.semester_name_snapshot,
            "academic_year":   sl.academic_year_snapshot,
            "sgpa":            str(sl.sgpa_snapshot)     if sl.sgpa_snapshot else "—",
            "cgpa":            str(sl.cgpa_snapshot)     if sl.cgpa_snapshot else "—",
            "credits_earned":  str(sl.credits_earned_snapshot) if sl.credits_earned_snapshot else "—",
            "overall_status":  sl.overall_result_status_snapshot or "—",
            "subjects": [
                {
                    "code":     s.course_code_snapshot or "",
                    "name":     s.course_name_snapshot or "",
                    "credits":  str(s.course_credits_snapshot) if s.course_credits_snapshot else "—",
                    "internal": _fmt_marks(s.internal_marks_snapshot),
                    "external": _fmt_marks(s.external_marks_snapshot),
                    "total":    _fmt_marks(s.total_marks_snapshot),
                    "grade":    s.grade_letter_snapshot or "—",
                    "result":   s.result_status_snapshot or "—",
                }
                for s in subjects_sorted
            ],
        })
    return out


def _fmt_marks(val) -> str:
    if val is None:
        return "—"
    return str(Decimal(str(val)).quantize(Decimal("0.00")))


def _render_pdf(ctx: dict) -> bytes:
    """Render transcript PDF using ReportLab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable, Paragraph, SimpleDocTemplate,
        Spacer, Table, TableStyle,
    )
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.barcode.qr import QrCodeWidget

    buf = io.BytesIO()
    PAGE_W, PAGE_H = A4
    MARGIN = 2 * cm

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Transcript — {ctx['transcript_number'] or 'DRAFT'}",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14,
                         spaceAfter=2, alignment=1)
    ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11,
                         spaceBefore=8, spaceAfter=4)
    normal = ParagraphStyle("N", parent=styles["Normal"], fontSize=8,
                              leading=11)
    small = ParagraphStyle("S", parent=styles["Normal"], fontSize=7, leading=9)
    center = ParagraphStyle("C", parent=styles["Normal"], fontSize=8,
                              leading=11, alignment=1)
    ParagraphStyle("B", parent=styles["Normal"], fontSize=8,
                           leading=11, fontName="Helvetica-Bold")

    story = []

    # ── Header ────────────────────────────────────────────────────────────
    story.append(Paragraph(ctx["institution_name"] or "Institution", h1))
    story.append(Paragraph(
        f"{ctx['transcript_type']} TRANSCRIPT",
        ParagraphStyle("TT", parent=h1, fontSize=12, textColor=colors.darkblue),
    ))
    if ctx.get("transcript_number"):
        story.append(Paragraph(
            f"Transcript No: <b>{ctx['transcript_number']}</b>",
            center,
        ))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 4))

    # ── Student Details ───────────────────────────────────────────────────
    student_data = [
        ["Student Name",  ctx["student_name"] or "—",
         "USN",           ctx["usn"] or "—"],
        ["Programme",     ctx["program_name"] or "—",
         "Batch",         ctx["batch_name"] or "—"],
        ["Degree",        ctx["degree_title"] or ctx["program_name"] or "—",
         "School / Dept", ctx["school_name"] or "—"],
    ]
    tbl = Table(student_data, colWidths=[3.5*cm, 6.5*cm, 3*cm, 4.5*cm])
    tbl.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME",  (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",  (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, -1), 8),
        ("VALIGN",    (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 4))

    # ── Semester tables ───────────────────────────────────────────────────
    hdr_row = ["Code", "Subject", "Cr", "Int", "Ext", "Total", "Grade", "Result"]
    col_w   = [1.7*cm, 7.2*cm, 0.8*cm, 1.1*cm, 1.1*cm, 1.3*cm, 1.2*cm, 1.3*cm]

    for sem in ctx.get("semesters", []):
        sem_label = sem.get("semester_name") or f"Semester {sem.get('semester_number', '?')}"
        ay_label  = sem.get("academic_year") or ""
        story.append(Paragraph(
            f"{sem_label}  —  {ay_label}",
            ParagraphStyle("SH", parent=styles["Normal"], fontSize=9,
                           fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=2),
        ))

        rows = [hdr_row]
        for s in sem.get("subjects", []):
            rows.append([
                s["code"], s["name"], s["credits"],
                s["internal"], s["external"], s["total"],
                s["grade"], s["result"],
            ])
        rows.append([
            "", "SGPA / CGPA", "", "", "",
            f"{sem['sgpa']} / {sem['cgpa']}",
            f"Cr. Earned: {sem['credits_earned']}", sem["overall_status"],
        ])

        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a3a6b")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 7),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.grey),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2),
             [colors.white, colors.HexColor("#f7f7f7")]),
            ("BACKGROUND",    (0, -1), (-1, -1), colors.HexColor("#e8edf4")),
            ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE",      (0, -1), (-1, -1), 7),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 4))

    # ── Summary row ───────────────────────────────────────────────────────
    summary_data = [
        ["Overall CGPA", ctx["overall_cgpa"], "Total Credits Earned",
         ctx["total_credits_earned"], "Active Arrears", str(ctx["arrear_count"])],
    ]
    st = Table(summary_data, colWidths=[3.5*cm, 2.5*cm, 4*cm, 2.5*cm, 3*cm, 2*cm])
    st.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME",  (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",  (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTNAME",  (4, 0), (4, -1),  "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, -1), 8),
        ("BACKGROUND",(0, 0), (-1, -1), colors.HexColor("#e8edf4")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(st)
    story.append(Spacer(1, 4))

    # ── Degree status advisory ────────────────────────────────────────────
    ds_color = (
        colors.darkgreen
        if ctx["degree_status"] in ("ELIGIBLE", "GRADUATED")
        else colors.darkred
    )
    story.append(Paragraph(
        f"<b>Degree Status (Advisory):</b> "
        f"<font color='{ds_color.hexval()}'>{ctx['degree_status']}</font>"
        f" — Subject to official academic board ratification.",
        ParagraphStyle("DS", parent=normal, spaceAfter=4),
    ))

    # ── QR code + verification footer ─────────────────────────────────────
    if ctx.get("verification_code"):
        verify_url = f"https://verify.vidya.edu/{ctx['verification_code']}"
        qr_widget = QrCodeWidget(verify_url)
        qr_bounds = qr_widget.getBounds()
        qr_w = qr_bounds[2] - qr_bounds[0]
        qr_h = qr_bounds[3] - qr_bounds[1]
        scale = (2.5 * cm) / max(qr_w, qr_h)
        d = Drawing(2.5*cm, 2.5*cm, transform=[scale, 0, 0, scale, 0, 0])
        d.add(qr_widget)

        qr_table = Table(
            [[d, Paragraph(
                f"<b>Verification Code:</b> {ctx['verification_code']}<br/>"
                f"Scan QR code or visit the institution's verification portal.<br/>"
                f"<i>This transcript is official only when issued by authorised personnel.</i>",
                small,
            )]],
            colWidths=[3*cm, PAGE_W - 2*MARGIN - 3*cm],
        )
        qr_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(qr_table)

    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<i>This document is computer-generated. Any alteration invalidates it.</i>",
        small,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _s3_put_object(data: bytes, s3_key: str) -> str:
    """Sync S3 upload. Called via asyncio.to_thread."""
    import boto3
    from botocore.exceptions import ClientError
    from app.config import settings

    client = boto3.client(
        "s3",
        endpoint_url         = settings.S3_ENDPOINT,
        aws_access_key_id    = settings.S3_ACCESS_KEY,
        aws_secret_access_key = settings.S3_SECRET_KEY,
        region_name          = "us-east-1",
    )
    bucket = settings.S3_BUCKET
    try:
        client.put_object(
            Bucket       = bucket,
            Key          = s3_key,
            Body         = data,
            ContentType  = "application/pdf",
        )
    except ClientError as exc:
        logger.error("S3 upload failed for %s: %s", s3_key, exc)
        raise
    return s3_key
