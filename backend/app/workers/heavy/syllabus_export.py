"""
M02 syllabus export task — PDF / DOCX / JSON.

Runs on the celery-heavy queue.  Export is only permitted for
FACULTY_APPROVED and ADMIN_LOCKED syllabi; the service layer enforces
this before dispatching, and this task double-checks on entry.

Data loaded per export:
  - Syllabus + outcomes (with CO-PO mappings) + units + references
  - Course metadata from M01 (code, title, credits, semester, L/T/P)
  - Programme outcomes from M01 (for CO-PO matrix column headers)
  - Only is_confirmed=True references appear in exports
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import sys
import uuid as uuid_module
from datetime import timezone
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m02.export")

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
    name="app.workers.heavy.export_syllabus",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def export_syllabus(
    *,
    job_id: str,
    syllabus_id: str,
    tenant_id: str,
    schema_name: str,
    export_format: str,
    requested_by_user_id: str,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_export(
            syllabus_id=UUID(syllabus_id),
            tenant_id=UUID(tenant_id),
            schema_name=schema_name,
            export_format=export_format,
            requested_by_user_id=UUID(requested_by_user_id),
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_export(
    syllabus_id: UUID,
    tenant_id: UUID,
    schema_name: str,
    export_format: str,
    requested_by_user_id: UUID,
) -> dict:
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.core.storage.models import StorageEntityType
    from app.core.storage.repository import StorageRepository
    from app.modules.m01_program_advisor.models import ProgramOutcome
    from app.modules.m01_program_advisor.repository import CourseRepository
    from app.modules.m02_syllabus.models import SyllabusStatus
    from app.modules.m02_syllabus.repository import SyllabusRepository

    tenant_slug = schema_name.removeprefix("tenant_")
    engine = _get_async_engine()

    _EXPORTABLE = {SyllabusStatus.FACULTY_APPROVED, SyllabusStatus.ADMIN_LOCKED}

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(text(f"SET search_path TO {schema_name}, public"))

            syllabus = await SyllabusRepository.get_detail(syllabus_id, db=session)
            if syllabus is None:
                raise ValueError(f"Syllabus {syllabus_id} not found.")
            if syllabus.status not in _EXPORTABLE:
                raise ValueError(
                    f"Syllabus {syllabus_id} is {syllabus.status.value}; "
                    "export requires FACULTY_APPROVED or ADMIN_LOCKED."
                )

            course = await CourseRepository.get_by_id(syllabus.course_id, db=session)
            if course is None:
                raise ValueError(f"Course {syllabus.course_id} not found in M01.")

            # Load programme outcomes for CO-PO matrix column headers
            po_stmt = (
                select(ProgramOutcome)
                .where(ProgramOutcome.program_id == course.program_id)
                .order_by(ProgramOutcome.display_order)
            )
            pos = list((await session.execute(po_stmt)).scalars().all())

            buf = io.BytesIO()
            if export_format == "pdf":
                content_type = "application/pdf"
                ext = "pdf"
                _generate_pdf(buf, syllabus, course, pos)
            elif export_format == "docx":
                content_type = (
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                )
                ext = "docx"
                _generate_docx(buf, syllabus, course, pos)
            else:
                content_type = "application/json"
                ext = "json"
                _generate_json(buf, syllabus, course, pos)

            buf.seek(0)
            file_bytes = buf.read()
            size_bytes = len(file_bytes)

            safe_code  = re.sub(r"[^a-z0-9_-]", "_", course.code.lower())[:20].strip("_")
            filename   = f"syllabus_{safe_code}_v{syllabus.version}.{ext}"
            file_uuid  = uuid_module.uuid4()
            object_key = (
                f"vidya-assets/{tenant_slug}/syllabus_export"
                f"/{syllabus_id}/{file_uuid}-{filename}"
            )

            await asyncio.to_thread(_s3_put_object, object_key, file_bytes, content_type)

            asset = await StorageRepository.create(
                uploaded_by_user_id=requested_by_user_id,
                entity_type=StorageEntityType.SYLLABUS_EXPORT.value,
                entity_id=syllabus_id,
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
            AuditEventType.SYLLABUS_EXPORT_COMPLETED,
            actor_user_id=requested_by_user_id,
            actor_role="SYSTEM",
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="Syllabus",
            target_id=str(syllabus_id),
            metadata={
                "asset_id":   str(asset.id),
                "format":     export_format,
                "size_bytes": size_bytes,
            },
        )

        logger.info(
            "m02.export: %s export complete (syllabus=%s size=%d)",
            export_format, syllabus_id, size_bytes,
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
                AuditEventType.SYLLABUS_EXPORT_FAILED,
                actor_user_id=requested_by_user_id,
                actor_role="SYSTEM",
                tenant_id=tenant_id,
                schema_name=schema_name,
                target_entity="Syllabus",
                target_id=str(syllabus_id),
                metadata={"error": str(exc)[:500], "format": export_format},
            )
        except Exception:
            logger.exception("m02.export: failed to log SYLLABUS_EXPORT_FAILED audit")
        raise


# ---------------------------------------------------------------------------
# S3 direct upload
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
# PDF generation (reportlab)
# ---------------------------------------------------------------------------

def _generate_pdf(buf, syllabus, course, pos):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
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

    _BLUE     = colors.HexColor("#2E4057")
    _ACCENT   = colors.HexColor("#4472C4")
    _ALT_ROW  = colors.HexColor("#EBF0FA")
    _STRENGTH = {"HIGH": "H", "MEDIUM": "M", "LOW": "L"}

    BASE_GRID = TableStyle([
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("BACKGROUND",    (0, 0), (-1, 0),  _ACCENT),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, _ALT_ROW]),
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID",     (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])

    styles  = getSampleStyleSheet()
    small   = ParagraphStyle("small",  parent=styles["Normal"], fontSize=8,  leading=10)
    tiny    = ParagraphStyle("tiny",   parent=styles["Normal"], fontSize=7,  leading=9)
    h1      = ParagraphStyle("h1sect", parent=styles["Heading1"], textColor=_BLUE)
    h2      = ParagraphStyle("h2sect", parent=styles["Heading2"], textColor=_ACCENT)

    # Use portrait for most; switch to landscape only for wide CO-PO matrix
    use_landscape = len(pos) > 8
    pagesize = landscape(A4) if use_landscape else A4
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize,
        topMargin=2*cm, bottomMargin=2*cm,
        leftMargin=2*cm, rightMargin=2*cm,
    )
    story = []

    # ── Cover ────────────────────────────────────────────────────────────────
    story.append(Paragraph(f"{course.code}: {course.title}", styles["Title"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Course Syllabus", styles["Heading2"]))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=_BLUE))
    story.append(Spacer(1, 0.4*cm))

    approved_at = (
        syllabus.approved_at.strftime("%Y-%m-%d") if syllabus.approved_at else "—"
    )
    locked_at = (
        syllabus.locked_at.strftime("%Y-%m-%d")   if syllabus.locked_at   else "—"
    )
    ltp = (
        f"{course.hours_lecture or 0}L / "
        f"{course.hours_tutorial or 0}T / "
        f"{course.hours_practical or 0}P"
    )
    meta_rows = [
        ["Course Code",    course.code],
        ["Course Title",   course.title],
        ["Credits",        str(course.credits)],
        ["Semester",       str(course.semester)],
        ["Hours (L/T/P)",  ltp],
        ["Syllabus Version", str(syllabus.version)],
        ["Status",         syllabus.status.value],
        ["Approved At",    approved_at],
        ["Locked At",      locked_at],
    ]
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

    # ── Course Outcomes ───────────────────────────────────────────────────────
    cos_sorted = sorted(syllabus.outcomes, key=lambda c: c.display_order)
    if cos_sorted:
        story.append(Paragraph("Course Outcomes", h1))
        story.append(Spacer(1, 0.3*cm))
        header = [["CO Code", "Description", "Bloom Level"]]
        rows = [
            [co.code, Paragraph(co.description, small), co.bloom_level.value if co.bloom_level else "—"]
            for co in cos_sorted
        ]
        t = Table(header + rows, colWidths=[2.2*cm, 11*cm, 3*cm])
        t.setStyle(BASE_GRID)
        story.append(t)
        story.append(Spacer(1, 1*cm))

    # ── CO-PO Mapping Matrix ──────────────────────────────────────────────────
    if cos_sorted and pos:
        story.append(Paragraph("CO–PO Mapping Matrix", h1))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(
            "H = High  |  M = Medium  |  L = Low  |  blank = No mapping",
            tiny,
        ))
        story.append(Spacer(1, 0.3*cm))

        po_map: dict[UUID, object] = {p.id: p for p in pos}
        mapping_index: dict[tuple, str] = {}
        for co in cos_sorted:
            for m in co.mappings:
                mapping_index[(co.id, m.po_id)] = m.mapping_strength.value

        col_w = max(1.2*cm, min(2*cm, 16*cm / (len(pos) + 1)))
        header = [["CO"] + [p.code for p in pos]]
        rows = []
        for co in cos_sorted:
            row = [co.code]
            for p in pos:
                strength = mapping_index.get((co.id, p.id), "")
                row.append(_STRENGTH.get(strength, ""))
            rows.append(row)

        matrix_style = TableStyle([
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
            ("FONTNAME",      (1, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("BACKGROUND",    (0, 0), (-1, 0),  _ACCENT),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("BACKGROUND",    (0, 1), (0, -1),  colors.HexColor("#F2F2F2")),
            ("ALIGN",         (1, 1), (-1, -1), "CENTER"),
            ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
            ("BOX",           (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID",     (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 3),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
        t = Table(
            header + rows,
            colWidths=[2*cm] + [col_w] * len(pos),
        )
        t.setStyle(matrix_style)
        story.append(t)
        story.append(Spacer(1, 1*cm))

    # ── Syllabus Units ────────────────────────────────────────────────────────
    units_sorted = sorted(syllabus.units, key=lambda u: u.unit_number)
    if units_sorted:
        story.append(Paragraph("Syllabus Units", h1))
        story.append(Spacer(1, 0.3*cm))
        for unit in units_sorted:
            story.append(Paragraph(
                f"Unit {unit.unit_number}: {unit.title}  ({unit.total_hours or '?'} hrs)",
                h2,
            ))
            if unit.pedagogy:
                story.append(Paragraph(f"Pedagogy: {unit.pedagogy}", small))
            topics = unit.topics or []
            for topic in topics:
                label = topic.get("title") or topic.get("name") or str(topic)
                sub   = topic.get("sub_topics") or topic.get("subtopics") or []
                story.append(Paragraph(f"• {label}", small))
                for s in sub:
                    story.append(Paragraph(f"    – {s}", tiny))
            story.append(Spacer(1, 0.5*cm))

    # ── References ────────────────────────────────────────────────────────────
    confirmed_refs = [r for r in syllabus.references if r.is_confirmed]
    if confirmed_refs:
        story.append(Paragraph("References", h1))
        story.append(Spacer(1, 0.3*cm))

        from collections import defaultdict
        by_type = defaultdict(list)
        for ref in confirmed_refs:
            by_type[ref.ref_type.value].append(ref)

        for rtype in ["TEXTBOOK", "REFERENCE", "JOURNAL", "ONLINE"]:
            rlist = by_type.get(rtype)
            if not rlist:
                continue
            story.append(Paragraph(rtype.capitalize() + "s", h2))
            for i, ref in enumerate(rlist, 1):
                authors = ", ".join(ref.authors) if ref.authors else "Unknown"
                year    = str(ref.year) if ref.year else "n.d."
                line    = f"{i}. {authors} ({year}). {ref.title}."
                if ref.publisher:
                    line += f" {ref.publisher}."
                if ref.doi:
                    line += f" DOI: {ref.doi}"
                elif ref.isbn:
                    line += f" ISBN: {ref.isbn}"
                elif ref.url:
                    line += f" URL: {ref.url}"
                story.append(Paragraph(line, small))
            story.append(Spacer(1, 0.4*cm))

    doc.build(story)


# ---------------------------------------------------------------------------
# DOCX generation (python-docx)
# ---------------------------------------------------------------------------

def _generate_docx(buf, syllabus, course, pos):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor
    from collections import defaultdict

    _STRENGTH = {"HIGH": "H", "MEDIUM": "M", "LOW": "L"}

    doc = Document()

    # ── Cover ─────────────────────────────────────────────────────────────────
    title_para = doc.add_heading(f"{course.code}: {course.title}", 0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("Course Syllabus")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.runs[0].bold = True

    doc.add_heading("Syllabus Details", 1)
    meta_t = doc.add_table(rows=0, cols=2)
    meta_t.style = "Table Grid"
    approved_at = syllabus.approved_at.strftime("%Y-%m-%d") if syllabus.approved_at else "—"
    locked_at   = syllabus.locked_at.strftime("%Y-%m-%d")   if syllabus.locked_at   else "—"
    ltp = (
        f"{course.hours_lecture or 0}L / "
        f"{course.hours_tutorial or 0}T / "
        f"{course.hours_practical or 0}P"
    )
    for label, value in [
        ("Course Code",       course.code),
        ("Course Title",      course.title),
        ("Credits",           str(course.credits)),
        ("Semester",          str(course.semester)),
        ("Hours (L/T/P)",     ltp),
        ("Syllabus Version",  str(syllabus.version)),
        ("Status",            syllabus.status.value),
        ("Approved At",       approved_at),
        ("Locked At",         locked_at),
    ]:
        row = meta_t.add_row()
        row.cells[0].text = label
        row.cells[1].text = value
    doc.add_paragraph()

    # ── Course Outcomes ───────────────────────────────────────────────────────
    cos_sorted = sorted(syllabus.outcomes, key=lambda c: c.display_order)
    if cos_sorted:
        doc.add_heading("Course Outcomes", 1)
        t = doc.add_table(rows=1, cols=3)
        t.style = "Table Grid"
        hdr = t.rows[0].cells
        hdr[0].text = "CO Code"
        hdr[1].text = "Description"
        hdr[2].text = "Bloom Level"
        for co in cos_sorted:
            row = t.add_row()
            row.cells[0].text = co.code
            row.cells[1].text = co.description
            row.cells[2].text = co.bloom_level.value if co.bloom_level else "—"
        doc.add_paragraph()

    # ── CO-PO Mapping Matrix ──────────────────────────────────────────────────
    if cos_sorted and pos:
        doc.add_heading("CO–PO Mapping Matrix", 1)
        doc.add_paragraph("H = High  |  M = Medium  |  L = Low  |  blank = No mapping")

        mapping_index: dict[tuple, str] = {}
        for co in cos_sorted:
            for m in co.mappings:
                mapping_index[(co.id, m.po_id)] = m.mapping_strength.value

        ncols = len(pos) + 1
        t = doc.add_table(rows=1, cols=ncols)
        t.style = "Table Grid"
        hdr = t.rows[0].cells
        hdr[0].text = "CO \\ PO"
        for i, po in enumerate(pos, 1):
            hdr[i].text = po.code

        for co in cos_sorted:
            row = t.add_row()
            row.cells[0].text = co.code
            for i, po in enumerate(pos, 1):
                strength = mapping_index.get((co.id, po.id), "")
                row.cells[i].text = _STRENGTH.get(strength, "")
        doc.add_paragraph()

    # ── Syllabus Units ────────────────────────────────────────────────────────
    units_sorted = sorted(syllabus.units, key=lambda u: u.unit_number)
    if units_sorted:
        doc.add_heading("Syllabus Units", 1)
        for unit in units_sorted:
            doc.add_heading(
                f"Unit {unit.unit_number}: {unit.title}  ({unit.total_hours or '?'} hrs)", 2
            )
            if unit.pedagogy:
                doc.add_paragraph(f"Pedagogy: {unit.pedagogy}")
            topics = unit.topics or []
            for topic in topics:
                label = topic.get("title") or topic.get("name") or str(topic)
                sub   = topic.get("sub_topics") or topic.get("subtopics") or []
                doc.add_paragraph(f"• {label}", style="List Bullet")
                for s in sub:
                    doc.add_paragraph(f"    – {s}")

    # ── References ────────────────────────────────────────────────────────────
    confirmed_refs = [r for r in syllabus.references if r.is_confirmed]
    if confirmed_refs:
        doc.add_heading("References", 1)
        by_type = defaultdict(list)
        for ref in confirmed_refs:
            by_type[ref.ref_type.value].append(ref)

        for rtype in ["TEXTBOOK", "REFERENCE", "JOURNAL", "ONLINE"]:
            rlist = by_type.get(rtype)
            if not rlist:
                continue
            doc.add_heading(rtype.capitalize() + "s", 2)
            for i, ref in enumerate(rlist, 1):
                authors = ", ".join(ref.authors) if ref.authors else "Unknown"
                year    = str(ref.year) if ref.year else "n.d."
                line    = f"{i}. {authors} ({year}). {ref.title}."
                if ref.publisher:
                    line += f" {ref.publisher}."
                if ref.doi:
                    line += f" DOI: {ref.doi}"
                elif ref.isbn:
                    line += f" ISBN: {ref.isbn}"
                elif ref.url:
                    line += f" URL: {ref.url}"
                doc.add_paragraph(line)

    doc.save(buf)


# ---------------------------------------------------------------------------
# JSON generation (machine-readable structured export)
# ---------------------------------------------------------------------------

def _generate_json(buf, syllabus, course, pos):
    from datetime import datetime

    def _dt(d):
        return d.isoformat() if d else None

    mapping_index: dict[tuple, dict] = {}
    for co in syllabus.outcomes:
        for m in co.mappings:
            mapping_index[(co.id, m.po_id)] = {
                "strength":     m.mapping_strength.value,
                "justification": m.justification,
            }

    cos_sorted   = sorted(syllabus.outcomes, key=lambda c: c.display_order)
    units_sorted = sorted(syllabus.units,    key=lambda u: u.unit_number)

    document = {
        "export_metadata": {
            "exported_at":  datetime.now(timezone.utc).isoformat(),
            "syllabus_id":  str(syllabus.id),
            "course_id":    str(syllabus.course_id),
            "version":      syllabus.version,
            "status":       syllabus.status.value,
            "approved_at":  _dt(syllabus.approved_at),
            "locked_at":    _dt(syllabus.locked_at),
            "ai_model":     syllabus.ai_model,
        },
        "course": {
            "id":              str(course.id),
            "code":            course.code,
            "title":           course.title,
            "credits":         course.credits,
            "semester":        course.semester,
            "hours_lecture":   course.hours_lecture,
            "hours_tutorial":  course.hours_tutorial,
            "hours_practical": course.hours_practical,
            "description":     course.description,
        },
        "course_outcomes": [
            {
                "id":            str(co.id),
                "code":          co.code,
                "description":   co.description,
                "bloom_level":   co.bloom_level.value if co.bloom_level else None,
                "display_order": co.display_order,
            }
            for co in cos_sorted
        ],
        "co_po_matrix": {
            "program_outcomes": [
                {
                    "id":            str(po.id),
                    "code":          po.code,
                    "description":   po.description,
                    "bloom_level":   po.bloom_level,
                    "display_order": po.display_order,
                }
                for po in pos
            ],
            "mappings": [
                {
                    "co_id":   str(co.id),
                    "co_code": co.code,
                    "po_mappings": {
                        str(po.id): mapping_index[(co.id, po.id)]
                        for po in pos
                        if (co.id, po.id) in mapping_index
                    },
                }
                for co in cos_sorted
            ],
        },
        "units": [
            {
                "id":           str(unit.id),
                "unit_number":  unit.unit_number,
                "title":        unit.title,
                "total_hours":  unit.total_hours,
                "pedagogy":     unit.pedagogy,
                "topics":       unit.topics or [],
                "bloom_summary": unit.bloom_summary or {},
            }
            for unit in units_sorted
        ],
        "references": [
            {
                "id":           str(ref.id),
                "title":        ref.title,
                "authors":      ref.authors or [],
                "year":         ref.year,
                "ref_type":     ref.ref_type.value,
                "source":       ref.source.value if ref.source else None,
                "doi":          ref.doi,
                "isbn":         ref.isbn,
                "url":          ref.url,
                "publisher":    ref.publisher,
                "is_confirmed": ref.is_confirmed,
            }
            for ref in syllabus.references
            if ref.is_confirmed
        ],
    }

    buf.write(json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8"))
