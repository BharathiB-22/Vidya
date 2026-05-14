"""
M03 course kit export task — PPTX (slide deck) / PDF (handout).

Runs on the celery-heavy queue.  Export is only permitted for
PUBLISHED and ARCHIVED kits; the service layer enforces this before
dispatching, and this task double-checks on entry.

Sensitive field gating (role-aware):
  - speaker_notes  — omitted for DEAN
  - answer_key     — omitted for DEAN
  - model_answer   — omitted for DEAN

Data loaded per export:
  - Kit detail (slides, quizlets, assignments, JSONB plan fields)
  - Syllabus (for course_id)
  - Course from M01 (code, title)
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import sys
import uuid as uuid_module
from datetime import timezone
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m03.export")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.export_course_kit",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def export_course_kit(
    *,
    job_id: str,
    kit_id: str,
    tenant_id: str,
    schema_name: str,
    export_format: str,
    requested_by_user_id: str,
    requested_by_role: str = "FACULTY",
    request_id: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_export(
            kit_id=UUID(kit_id),
            tenant_id=UUID(tenant_id),
            schema_name=schema_name,
            export_format=export_format,
            requested_by_user_id=UUID(requested_by_user_id),
            requested_by_role=requested_by_role,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_export(
    kit_id: UUID,
    tenant_id: UUID,
    schema_name: str,
    export_format: str,
    requested_by_user_id: UUID,
    requested_by_role: str,
) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.core.storage.models import StorageEntityType
    from app.core.storage.repository import StorageRepository
    from app.modules.m01_program_advisor.repository import CourseRepository
    from app.modules.m02_syllabus.repository import SyllabusRepository
    from app.modules.m03_course_kit.models import CourseKitStatus
    from app.modules.m03_course_kit.repository import CourseKitRepository

    tenant_slug = schema_name.removeprefix("tenant_")
    engine = _get_async_engine()
    is_dean = requested_by_role == "DEAN"

    _EXPORTABLE = {CourseKitStatus.PUBLISHED, CourseKitStatus.ARCHIVED}

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(text(f"SET search_path TO {schema_name}, public"))

            kit = await CourseKitRepository.get_detail(kit_id, db=session)
            if kit is None:
                raise ValueError(f"Course kit {kit_id} not found.")
            if kit.status not in _EXPORTABLE:
                raise ValueError(
                    f"Course kit {kit_id} is {kit.status.value}; "
                    "export requires PUBLISHED or ARCHIVED status."
                )

            syllabus = await SyllabusRepository.get_by_id(kit.syllabus_id, db=session)
            if syllabus is None:
                raise ValueError(f"Syllabus {kit.syllabus_id} not found.")

            course = await CourseRepository.get_by_id(syllabus.course_id, db=session)
            if course is None:
                raise ValueError(f"Course {syllabus.course_id} not found in M01.")

            buf = io.BytesIO()
            if export_format == "pptx":
                content_type = (
                    "application/vnd.openxmlformats-officedocument"
                    ".presentationml.presentation"
                )
                ext = "pptx"
                _generate_pptx(buf, kit, course, is_dean=is_dean)
            else:
                content_type = "application/pdf"
                ext = "pdf"
                _generate_pdf(buf, kit, course, is_dean=is_dean)

            buf.seek(0)
            file_bytes = buf.read()
            size_bytes = len(file_bytes)

            safe_code = re.sub(r"[^a-z0-9_-]", "_", course.code.lower())[:20].strip("_")
            filename   = f"kit_{safe_code}_u{kit.unit_number}_v{kit.version}.{ext}"
            file_uuid  = uuid_module.uuid4()
            object_key = (
                f"vidya-assets/{tenant_slug}/course_kit_export"
                f"/{kit_id}/{file_uuid}-{filename}"
            )

            await asyncio.to_thread(_s3_put_object, object_key, file_bytes, content_type)

            asset = await StorageRepository.create(
                uploaded_by_user_id=requested_by_user_id,
                entity_type=StorageEntityType.COURSE_KIT_EXPORT.value,
                entity_id=kit_id,
                object_key=object_key,
                original_filename=filename,
                size_bytes=size_bytes,
                content_type=content_type,
                db=session,
            )
            await session.commit()

        download_url = await StorageRepository.generate_presigned_get_url(
            object_key=object_key,
            expires_in_seconds=86_400,
        )

        await AuditService.log(
            AuditEventType.COURSE_KIT_EXPORT_COMPLETED,
            actor_user_id=requested_by_user_id,
            actor_role="SYSTEM",
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="CourseKit",
            target_id=str(kit_id),
            metadata={
                "asset_id":   str(asset.id),
                "format":     export_format,
                "size_bytes": size_bytes,
            },
        )

        logger.info(
            "m03.export: %s export complete (kit=%s size=%d)",
            export_format, kit_id, size_bytes,
        )

        return {
            "download_url": download_url,
            "asset_id":     str(asset.id),
            "format":       export_format,
            "size_bytes":   size_bytes,
        }

    except Exception as exc:
        try:
            await AuditService.log(
                AuditEventType.COURSE_KIT_EXPORT_FAILED,
                actor_user_id=requested_by_user_id,
                actor_role="SYSTEM",
                tenant_id=tenant_id,
                schema_name=schema_name,
                target_entity="CourseKit",
                target_id=str(kit_id),
                metadata={"error": str(exc)[:500], "format": export_format},
            )
        except Exception:
            logger.exception("m03.export: failed to log COURSE_KIT_EXPORT_FAILED audit")
        raise


# ---------------------------------------------------------------------------
# S3 direct upload (worker has credentials — no presigned PUT needed)
# ---------------------------------------------------------------------------

def _s3_put_object(object_key: str, file_bytes: bytes, content_type: str) -> None:
    import boto3
    from app.config import settings

    client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        use_ssl=settings.S3_USE_SSL,
    )
    client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=object_key,
        Body=file_bytes,
        ContentType=content_type,
    )


# ---------------------------------------------------------------------------
# PPTX generation (python-pptx)
# ---------------------------------------------------------------------------

def _generate_pptx(buf, kit, course, *, is_dean: bool) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    _BLUE   = RGBColor(0x2E, 0x40, 0x57)

    prs = Presentation()
    prs.slide_width  = Inches(13.33)   # widescreen 16:9
    prs.slide_height = Inches(7.5)

    title_layout   = prs.slide_layouts[0]   # Title Slide
    content_layout = prs.slide_layouts[1]   # Title and Content

    # ── Title slide ───────────────────────────────────────────────────────
    slide = prs.slides.add_slide(title_layout)
    slide.shapes.title.text = f"{course.code}: {course.title}"
    subtitle_ph = slide.placeholders[1]
    subtitle_ph.text = (
        f"Unit {kit.unit_number}  |  Version {kit.version}  |  "
        f"Status: {kit.status.value}  |  Complexity: {kit.complexity_level.value}"
    )
    for para in slide.shapes.title.text_frame.paragraphs:
        for run in para.runs:
            run.font.color.rgb = _BLUE
            run.font.size = Pt(28)

    # ── Kit slides ────────────────────────────────────────────────────────
    slides_sorted = sorted(kit.slides or [], key=lambda s: s.slide_number)
    for kit_slide in slides_sorted:
        sl = prs.slides.add_slide(content_layout)
        sl.shapes.title.text = kit_slide.title or f"Slide {kit_slide.slide_number}"

        content     = kit_slide.content or {}
        bullets     = content.get("bullets") or []
        key_concepts = content.get("key_concepts") or []

        tf = sl.placeholders[1].text_frame
        tf.clear()
        for i, bullet in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text  = bullet
            p.level = 0
            for run in p.runs:
                run.font.size = Pt(18)

        if key_concepts:
            p = tf.add_paragraph()
            p.text  = ""
            p = tf.add_paragraph()
            p.text  = "Key Concepts: " + "  |  ".join(key_concepts)
            p.level = 1
            for run in p.runs:
                run.font.size  = Pt(14)
                run.font.bold  = True

        # Speaker notes: faculty/admin see instructor notes; DEAN sees only meta
        notes_parts = []
        if not is_dean and kit_slide.speaker_notes:
            notes_parts.append(kit_slide.speaker_notes)
        if kit_slide.bloom_level:
            notes_parts.append(f"Bloom: {kit_slide.bloom_level.value}")
        if kit_slide.co_reference:
            notes_parts.append(f"CO: {kit_slide.co_reference}")
        if notes_parts:
            sl.notes_slide.notes_text_frame.text = "\n".join(notes_parts)

    # ── Teaching plan summary ─────────────────────────────────────────────
    teaching_plan = kit.teaching_plan or []
    if teaching_plan:
        sl = prs.slides.add_slide(content_layout)
        sl.shapes.title.text = "Weekly Teaching Plan"
        tf = sl.placeholders[1].text_frame
        tf.clear()
        for i, week in enumerate(teaching_plan):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            hours = week.get("hours", "?")
            p.text  = f"Week {week.get('week','?')}: {week.get('topic','')}  ({hours} hrs)"
            p.level = 0
            objectives = week.get("objectives") or []
            for obj in objectives[:2]:  # show up to 2 objectives per week
                sub = tf.add_paragraph()
                sub.text  = f"  {obj}"
                sub.level = 1

    # ── Resources ─────────────────────────────────────────────────────────
    resources = kit.resources or []
    if resources:
        sl = prs.slides.add_slide(content_layout)
        sl.shapes.title.text = "Teaching Resources"
        tf = sl.placeholders[1].text_frame
        tf.clear()
        for i, res in enumerate(resources):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            rtype = res.get("resource_type", "")
            title_str = res.get("title", "")
            p.text  = f"[{rtype}] {title_str}"
            p.level = 0
            url = res.get("url")
            if url:
                sub = tf.add_paragraph()
                sub.text  = url
                sub.level = 1

    prs.save(buf)


# ---------------------------------------------------------------------------
# PDF generation (reportlab — slide handout + kit content)
# ---------------------------------------------------------------------------

def _generate_pdf(buf, kit, course, *, is_dean: bool) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _BLUE   = colors.HexColor("#2E4057")
    _ACCENT = colors.HexColor("#4472C4")
    _ALT    = colors.HexColor("#EBF0FA")

    BASE_GRID = TableStyle([
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("BACKGROUND",    (0, 0), (-1, 0),  _ACCENT),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, _ALT]),
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID",     (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])

    styles = getSampleStyleSheet()
    small  = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10)
    tiny   = ParagraphStyle("tiny",  parent=styles["Normal"], fontSize=7, leading=9)
    h1     = ParagraphStyle("h1",    parent=styles["Heading1"], textColor=_BLUE)
    h2     = ParagraphStyle("h2",    parent=styles["Heading2"], textColor=_ACCENT)

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2*cm, bottomMargin=2*cm,
        leftMargin=2*cm, rightMargin=2*cm,
    )
    story = []

    # ── Cover ─────────────────────────────────────────────────────────────
    story.append(Paragraph(f"{course.code}: {course.title}", styles["Title"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Unit {kit.unit_number} — Teaching Kit", styles["Heading2"]
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=_BLUE))
    story.append(Spacer(1, 0.4*cm))

    meta_rows = [
        ["Course Code",  course.code],
        ["Course Title", course.title],
        ["Unit",         str(kit.unit_number)],
        ["Kit Version",  str(kit.version)],
        ["Status",       kit.status.value],
        ["Complexity",   kit.complexity_level.value],
    ]
    if kit.published_at:
        meta_rows.append(["Published At", kit.published_at.strftime("%Y-%m-%d")])
    if kit.ai_model:
        meta_rows.append(["AI Model", kit.ai_model])

    meta_t = Table(meta_rows, colWidths=[4.5*cm, 10*cm])
    meta_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID",     (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 1*cm))

    # ── Slides ────────────────────────────────────────────────────────────
    slides_sorted = sorted(kit.slides or [], key=lambda s: s.slide_number)
    if slides_sorted:
        story.append(Paragraph("Slides", h1))
        story.append(Spacer(1, 0.3*cm))

        for kit_slide in slides_sorted:
            story.append(Paragraph(
                f"Slide {kit_slide.slide_number}: {kit_slide.title or '(untitled)'}",
                h2,
            ))
            content      = kit_slide.content or {}
            bullets      = content.get("bullets") or []
            key_concepts = content.get("key_concepts") or []

            for bullet in bullets:
                story.append(Paragraph(f"• {bullet}", small))
            if key_concepts:
                story.append(Paragraph(
                    "Key concepts: " + "  |  ".join(key_concepts), tiny
                ))

            footer_parts = []
            if kit_slide.bloom_level:
                footer_parts.append(f"Bloom: {kit_slide.bloom_level.value}")
            if kit_slide.co_reference:
                footer_parts.append(f"CO: {kit_slide.co_reference}")
            if footer_parts:
                story.append(Paragraph(" | ".join(footer_parts), tiny))
            if not is_dean and kit_slide.speaker_notes:
                story.append(Paragraph(
                    f"[Notes] {kit_slide.speaker_notes}", tiny
                ))
            story.append(Spacer(1, 0.4*cm))

        story.append(PageBreak())

    # ── Weekly teaching plan ──────────────────────────────────────────────
    teaching_plan = kit.teaching_plan or []
    if teaching_plan:
        story.append(Paragraph("Weekly Teaching Plan", h1))
        story.append(Spacer(1, 0.3*cm))
        header = [["Week", "Topic", "Hours", "CO References"]]
        rows = []
        for week in teaching_plan:
            co_refs = ", ".join(week.get("co_references") or []) or "—"
            rows.append([
                str(week.get("week", "?")),
                Paragraph(week.get("topic", ""), small),
                str(week.get("hours", "?")),
                Paragraph(co_refs, small),
            ])
        t = Table(header + rows, colWidths=[1.5*cm, 8*cm, 2*cm, 4*cm])
        t.setStyle(BASE_GRID)
        story.append(t)
        story.append(Spacer(1, 1*cm))

    # ── Quizlets ──────────────────────────────────────────────────────────
    quizlets_sorted = sorted(kit.quizlets or [], key=lambda q: q.question_number)
    if quizlets_sorted:
        story.append(Paragraph("Quizlets", h1))
        story.append(Spacer(1, 0.3*cm))
        for qz in quizlets_sorted:
            story.append(Paragraph(
                f"Q{qz.question_number}. [{qz.question_type.value}] {qz.question_text}",
                small,
            ))
            for opt in (qz.options or []):
                if isinstance(opt, dict):
                    story.append(Paragraph(
                        f"  ({opt.get('label','?')}) {opt.get('text','')}", tiny
                    ))
            if not is_dean and qz.answer_key:
                story.append(Paragraph(f"  Answer: {qz.answer_key}", tiny))
            if qz.answer_explanation:
                story.append(Paragraph(
                    f"  Explanation: {qz.answer_explanation}", tiny
                ))
            story.append(Spacer(1, 0.3*cm))
        story.append(PageBreak())

    # ── Assignments ───────────────────────────────────────────────────────
    assignments_sorted = sorted(
        kit.assignments or [], key=lambda a: a.assignment_number
    )
    if assignments_sorted:
        story.append(Paragraph("Assignments", h1))
        story.append(Spacer(1, 0.3*cm))
        for asn in assignments_sorted:
            story.append(Paragraph(
                f"Assignment {asn.assignment_number}: {asn.title}", h2
            ))
            story.append(Paragraph(
                f"Type: {asn.assignment_type.value}  |  "
                f"Complexity: {asn.complexity_level.value}",
                tiny,
            ))
            story.append(Paragraph(asn.question_text, small))
            if not is_dean and asn.model_answer:
                story.append(Paragraph(f"Model Answer: {asn.model_answer}", small))
            rubric = asn.rubric or []
            if rubric and not is_dean:
                story.append(Paragraph("Rubric:", small))
                rub_h = [["Criterion", "Description", "Marks"]]
                rub_rows = [
                    [
                        Paragraph(r.get("criterion", ""), small),
                        Paragraph(r.get("description", ""), small),
                        str(r.get("max_marks", "")),
                    ]
                    for r in rubric if isinstance(r, dict)
                ]
                rub_t = Table(rub_h + rub_rows, colWidths=[3.5*cm, 9.5*cm, 2.5*cm])
                rub_t.setStyle(BASE_GRID)
                story.append(rub_t)
            story.append(Spacer(1, 0.5*cm))

    # ── Teaching Resources ────────────────────────────────────────────────
    resources = kit.resources or []
    if resources:
        story.append(Paragraph("Teaching Resources", h1))
        story.append(Spacer(1, 0.3*cm))
        for res in resources:
            rtype     = res.get("resource_type", "")
            title_str = res.get("title", "")
            url       = res.get("url")
            desc      = res.get("description")
            story.append(Paragraph(f"• [{rtype}] {title_str}", small))
            if desc:
                story.append(Paragraph(f"  {desc}", tiny))
            if url:
                story.append(Paragraph(f"  {url}", tiny))

    doc.build(story)
