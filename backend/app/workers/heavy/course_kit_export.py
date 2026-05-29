"""
M03 course kit export task â€” PPTX (slide deck) / PDF (handout).

Runs on the celery-heavy queue.  Export is only permitted for
PUBLISHED and ARCHIVED kits; the service layer enforces this before
dispatching, and this task double-checks on entry.

Sensitive field gating (role-aware):
  - speaker_notes  â€” omitted for DEAN
  - answer_key     â€” omitted for DEAN
  - model_answer   â€” omitted for DEAN

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
        from sqlalchemy.pool import NullPool
        from app.config import settings
        # NullPool: no connection caching between asyncio.run() calls.
        # On Windows --pool=solo each task runs in a fresh event loop; pooled
        # asyncpg connections attached to the previous (closed) loop raise
        # "Future attached to a different loop". NullPool prevents this.
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.export_course_kit",
    autoretry_for=(),
    max_retries=0,
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

            # Fetch enrichment data for professional PPTX (tenant branding, COs, faculty name)
            _t_row = (await session.execute(
                text("SELECT name, logo_url, primary_color FROM public.tenants WHERE id = :tid"),
                {"tid": str(tenant_id)},
            )).mappings().one_or_none()
            _pptx_inst   = _t_row["name"]          if _t_row else None
            _pptx_logo   = _t_row["logo_url"]       if _t_row else None
            _pptx_color  = _t_row["primary_color"]  if _t_row else None

            from app.modules.m02_syllabus.repository import CourseOutcomeRepository
            _pptx_cos = await CourseOutcomeRepository.list_by_syllabus(syllabus.id, db=session)

            _u_row = (await session.execute(
                text("SELECT full_name FROM users WHERE id = :uid"),
                {"uid": str(requested_by_user_id)},
            )).mappings().one_or_none()
            _pptx_faculty = _u_row["full_name"] if _u_row else None

            buf = io.BytesIO()
            if export_format == "pptx":
                content_type = (
                    "application/vnd.openxmlformats-officedocument"
                    ".presentationml.presentation"
                )
                ext = "pptx"
                _generate_pptx(buf, kit, course, is_dean=is_dean,
                                cos=_pptx_cos, institution_name=_pptx_inst,
                                logo_url=_pptx_logo, primary_color=_pptx_color,
                                faculty_name=_pptx_faculty)
            elif export_format == "handout":
                content_type = "application/pdf"
                ext = "pdf"
                _generate_handout_pdf(buf, kit, course)
            else:  # "pdf"
                content_type = "application/pdf"
                ext = "pdf"
                _generate_pdf(buf, kit, course, is_dean=is_dean)

            buf.seek(0)
            file_bytes = buf.read()
            size_bytes = len(file_bytes)

            safe_code = re.sub(r"[^a-z0-9_-]", "_", course.code.lower())[:20].strip("_")
            suffix    = "_handout" if export_format == "handout" else ""
            filename  = f"kit_{safe_code}_u{kit.unit_number}_v{kit.version}{suffix}.{ext}"
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
# S3 direct upload (worker has credentials â€” no presigned PUT needed)
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
    s3_key = object_key.removeprefix(f"{settings.S3_BUCKET}/")
    client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type,
    )


# ---------------------------------------------------------------------------
# PPTX generation â€” university-quality lecture deck
# ---------------------------------------------------------------------------

def _generate_pptx(buf, kit, course, *, is_dean: bool,
                   cos=None, institution_name=None, logo_url=None,
                   primary_color=None, faculty_name=None) -> None:
    from datetime import date as _date
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN

    # â”€â”€ Theme colours â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _NAV  = RGBColor(0x0F, 0x20, 0x44)   # navy  â€“ cover bg / header bars
    _ACC  = RGBColor(0x25, 0x63, 0xEB)   # blue  â€“ accent / key-concepts
    _TEAL = RGBColor(0x08, 0x91, 0xB2)   # teal  â€“ examples / resources
    _GRN  = RGBColor(0x05, 0x78, 0x50)   # green â€“ summary / definitions
    _ORG  = RGBColor(0x92, 0x40, 0x0E)   # orange â€“ quiz slides
    _WHT  = RGBColor(0xFF, 0xFF, 0xFF)
    _TXT  = RGBColor(0x1E, 0x29, 0x3B)   # dark slate
    _GRY  = RGBColor(0x64, 0x74, 0x8B)   # medium grey
    _LGRY = RGBColor(0xF1, 0xF5, 0xF9)   # light grey (table alternates)

    if primary_color and primary_color.startswith('#') and len(primary_color) == 7:
        try:
            h = primary_color.lstrip('#')
            _ACC = RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except Exception:
            pass

    prs = Presentation()
    W = prs.slide_width  = Inches(13.33)
    H = prs.slide_height = Inches(7.5)
    BLANK = prs.slide_layouts[6]

    def _clear_placeholders(slide) -> None:
        for ph in list(slide.placeholders):
            sp = ph._element
            sp.getparent().remove(sp)

    # â”€â”€ Low-level helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _bg(slide, c: RGBColor):
        f = slide.background.fill
        f.solid(); f.fore_color.rgb = c

    def _rect(slide, l, t, w, h, c: RGBColor):
        s = slide.shapes.add_shape(1, l, t, w, h)
        s.fill.solid(); s.fill.fore_color.rgb = c
        s.line.fill.background()
        return s

    def _txt(slide, text: str, l, t, w, h, *,
             sz=16, bold=False, italic=False,
             color: RGBColor = None, align=PP_ALIGN.LEFT):
        box = slide.shapes.add_textbox(l, t, w, h)
        tf  = box.text_frame
        tf.word_wrap = True
        p   = tf.paragraphs[0]
        p.alignment = align
        r   = p.add_run()
        r.text = text
        r.font.size = Pt(sz); r.font.bold = bold
        r.font.italic = italic
        r.font.color.rgb = color or _TXT
        return box

    def _header(slide, title: str, subtitle: str = '', color: RGBColor = None):
        hc = color or _NAV
        _rect(slide, 0, 0, W, Inches(1.02), hc)
        if subtitle:
            _txt(slide, subtitle, Inches(0.5), Inches(0.06),
                 Inches(12), Inches(0.3), sz=9, color=_GRY)
        _txt(slide, title, Inches(0.5), Inches(0.3), Inches(11.5), Inches(0.65),
             sz=24, bold=True, color=_WHT)

    def _tbl_hdr(table, headers, col_widths, hdr_color: RGBColor):
        for ci, (hd, cw) in enumerate(zip(headers, col_widths)):
            table.columns[ci].width = cw
            cell = table.cell(0, ci)
            cell.text = hd
            cell.fill.solid(); cell.fill.fore_color.rgb = hdr_color
            for p2 in cell.text_frame.paragraphs:
                for r2 in p2.runs:
                    r2.font.size = Pt(10); r2.font.bold = True
                    r2.font.color.rgb = _WHT

    def _tbl_row(table, ri, values, alt_color: RGBColor = None):
        for ci, val in enumerate(values):
            cell = table.cell(ri, ci)
            cell.text = str(val)
            if ri % 2 == 0 and alt_color:
                cell.fill.solid(); cell.fill.fore_color.rgb = alt_color
            for p2 in cell.text_frame.paragraphs:
                for r2 in p2.runs:
                    r2.font.size = Pt(10); r2.font.color.rgb = _TXT

    effective_cos = cos or []
    slides_sorted = sorted(kit.slides or [], key=lambda s: s.slide_number)
    tp = kit.teaching_plan or []

    # â”€â”€ 1. COVER SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    sl = prs.slides.add_slide(BLANK)
    _clear_placeholders(sl)
    _bg(sl, _NAV)
    _rect(sl, 0, 0, Inches(0.22), H, _ACC)     # left accent strip

    logo_placed = False
    if logo_url:
        try:
            import urllib.request, io as _io
            with urllib.request.urlopen(logo_url, timeout=5) as resp:
                logo_bytes = resp.read()
            sl.shapes.add_picture(_io.BytesIO(logo_bytes),
                Inches(10.8), Inches(0.3), height=Inches(0.85))
            logo_placed = True
        except Exception:
            pass

    if institution_name:
        _txt(sl, institution_name.upper(),
             Inches(0.55), Inches(0.38),
             Inches(10 if logo_placed else 12.3), Inches(0.38),
             sz=11, bold=True, color=RGBColor(0x94, 0xA3, 0xB8))

    _txt(sl, course.code, Inches(0.55), Inches(1.7),
         Inches(12.3), Inches(0.55), sz=20, bold=True, color=_ACC)
    _txt(sl, course.title, Inches(0.55), Inches(2.3),
         Inches(12.3), Inches(1.05), sz=36, bold=True, color=_WHT)
    _txt(sl, f"Unit {kit.unit_number}", Inches(0.55), Inches(3.55),
         Inches(10), Inches(0.55), sz=20, color=RGBColor(0x94, 0xA3, 0xB8))

    _rect(sl, Inches(0.55), Inches(4.3), Inches(10), Inches(0.03), _ACC)

    meta_parts = []
    if faculty_name and not is_dean:
        meta_parts.append(faculty_name)
    meta_parts += [f"Version {kit.version}", kit.complexity_level.value,
                   _date.today().strftime('%B %Y')]
    _txt(sl, '  Â·  '.join(meta_parts), Inches(0.55), Inches(4.48),
         Inches(12.3), Inches(0.45), sz=12, color=RGBColor(0x94, 0xA3, 0xB8))

    # â”€â”€ 2. OBJECTIVES SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    sl = prs.slides.add_slide(BLANK)
    _clear_placeholders(sl)
    _bg(sl, _WHT)
    _header(sl, f"Unit {kit.unit_number} â€” Objectives & Schedule",
            subtitle=f'{course.code}: {course.title}')

    # COs (left column)
    _rect(sl, Inches(0.4), Inches(1.1), Inches(6.1), Inches(0.25), _ACC)
    _txt(sl, 'COURSE OUTCOMES', Inches(0.4), Inches(1.1),
         Inches(6.1), Inches(0.25), sz=8, bold=True, color=_WHT, align=PP_ALIGN.CENTER)
    for i, co in enumerate(effective_cos[:8]):
        yt = Inches(1.42 + i * 0.62)
        _rect(sl, Inches(0.4), yt, Inches(0.85), Inches(0.44), _LGRY)
        _txt(sl, getattr(co, 'code', ''), Inches(0.4), yt,
             Inches(0.85), Inches(0.44), sz=10, bold=True, color=_ACC, align=PP_ALIGN.CENTER)
        _txt(sl, getattr(co, 'description', ''),
             Inches(1.35), yt, Inches(4.9), Inches(0.3), sz=11, color=_TXT)
        bl = getattr(co, 'bloom_level', '')
        blstr = bl.value if hasattr(bl, 'value') else str(bl)
        _txt(sl, blstr, Inches(1.35), yt + Inches(0.3),
             Inches(4.9), Inches(0.2), sz=8, italic=True, color=_GRY)

    # Weekly schedule table (right column)
    if tp:
        _rect(sl, Inches(6.8), Inches(1.1), Inches(6.1), Inches(0.25), _NAV)
        _txt(sl, 'WEEKLY SCHEDULE', Inches(6.8), Inches(1.1),
             Inches(6.1), Inches(0.25), sz=8, bold=True, color=_WHT, align=PP_ALIGN.CENTER)
        n = min(len(tp), 9)
        tbl = sl.shapes.add_table(
            n + 1, 3, Inches(6.8), Inches(1.4), Inches(6.1), Inches(n * 0.56 + 0.44)
        ).table
        _tbl_hdr(tbl, ('Week', 'Topic', 'Hrs'),
                 (Inches(0.85), Inches(4.05), Inches(1.2)), _NAV)
        for ri, wk in enumerate(tp[:n], 1):
            _tbl_row(tbl, ri, [
                str(wk.get('week', ri)),
                str(wk.get('topic', ''))[:55],
                str(wk.get('hours', 'â€”')),
            ], _LGRY)

    # â”€â”€ 3. CONTENT SLIDES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    for ks in slides_sorted:
        sl = prs.slides.add_slide(BLANK)
        _clear_placeholders(sl)
        _bg(sl, _WHT)

        content  = ks.content or {}
        stype    = (content.get('slide_type') or '').upper()
        hcol     = {'SUMMARY': _GRN, 'QUIZ': _ORG, 'ACTIVITY': _TEAL}.get(stype, _NAV)

        _header(sl,
                ks.title or f"Slide {ks.slide_number}",
                subtitle=f'{course.code}  Â·  Unit {kit.unit_number}  Â·  Slide {ks.slide_number}',
                color=hcol)

        if stype:
            _rect(sl, Inches(11.15), Inches(0.08), Inches(1.95), Inches(0.27), _ACC)
            _txt(sl, stype, Inches(11.15), Inches(0.1), Inches(1.95), Inches(0.27),
                 sz=8, bold=True, color=_WHT, align=PP_ALIGN.CENTER)

        # Extract and normalise all content fields.
        # Defensive: coerce every item to str; handle empty/missing JSONB.
        bullets        = [str(b) for b in (content.get('bullets') or []) if b]
        key_concepts   = [str(k) for k in (content.get('key_concepts') or []) if k]
        definitions    = [str(d) for d in (content.get('definitions') or []) if d]
        examples       = [str(e) for e in (content.get('examples') or []) if e]
        code_snippet   = (content.get('code_snippet') or '').strip()
        activity       = (content.get('classroom_activity') or '').strip()
        summary_txt    = (content.get('student_summary') or '').strip()
        teaching_notes = (content.get('teaching_notes') or '').strip()

        # Fallback 1: try alternate field names Groq sometimes uses
        if not bullets:
            for _fk in ('points', 'body_points', 'slide_points', 'learning_points',
                        'content_points', 'teaching_points', 'body', 'slide_body'):
                _fv = content.get(_fk)
                if isinstance(_fv, list) and _fv:
                    bullets = [str(x) for x in _fv[:7] if x]
                    break
                elif isinstance(_fv, str) and _fv.strip():
                    bullets = [_fv.strip()]
                    break

        # Fallback 2: split speaker_notes into bullet lines
        if not bullets and ks.speaker_notes:
            _note_lines = [ln.strip() for ln in ks.speaker_notes.split('\n') if ln.strip()]
            if _note_lines:
                bullets = _note_lines[:5]

        # Fallback 3: synthesise from rich fields so body is never blank
        if not bullets:
            if key_concepts:
                bullets = ['Key concept: ' + kc for kc in key_concepts[:4]]
            elif definitions:
                bullets = [d[:140] for d in definitions[:3]]
            elif examples:
                bullets = ['Example: ' + ex for ex in examples[:3]]
            elif activity:
                bullets = [activity[:140]]
            elif summary_txt:
                bullets = [summary_txt[:140]]
            elif teaching_notes:
                bullets = [teaching_notes[:140]]
            else:
                bullets = [
                    'Unit ' + str(kit.unit_number) + ' - Slide ' + str(ks.slide_number)
                    + ': open Course Kit to add content before presenting'
                ]

        # Main bullets rendered as editable text boxes (left 2/3 of slide)
        by = Inches(1.15)
        for bullet in bullets[:7]:
            _txt(sl, '  ' + str(bullet), Inches(0.45), by,
                 Inches(8.25), Inches(0.65), sz=14, color=_TXT)
            by += Inches(0.68)

        if activity and len(bullets) < 5:
            _rect(sl, Inches(0.45), by + Inches(0.1), Inches(8.25), Inches(0.26), _TEAL)
            _txt(sl, 'Activity: ' + activity, Inches(0.55), by + Inches(0.1),
                 Inches(8.1), Inches(0.26), sz=9, bold=True, color=_WHT)

        # Right panel â€” key concepts + definitions
        ry = Inches(1.15)
        if key_concepts:
            _rect(sl, Inches(8.9), ry, Inches(4.1), Inches(0.25), _ACC)
            _txt(sl, 'KEY CONCEPTS', Inches(8.9), ry,
                 Inches(4.1), Inches(0.25), sz=8, bold=True, color=_WHT, align=PP_ALIGN.CENTER)
            ry += Inches(0.3)
            for kc in key_concepts[:5]:
                _txt(sl, f'â€¢ {kc}', Inches(8.95), ry,
                     Inches(4.0), Inches(0.4), sz=11, bold=True, color=_ACC)
                ry += Inches(0.43)
            ry += Inches(0.1)

        if definitions:
            _rect(sl, Inches(8.9), ry, Inches(4.1), Inches(0.25), _GRN)
            _txt(sl, 'DEFINITIONS', Inches(8.9), ry,
                 Inches(4.1), Inches(0.25), sz=8, bold=True, color=_WHT, align=PP_ALIGN.CENTER)
            ry += Inches(0.3)
            for d in definitions[:3]:
                _txt(sl, f'âž¤  {d}', Inches(8.95), ry,
                     Inches(4.0), Inches(0.52), sz=10, color=_TXT)
                ry += Inches(0.55)

        # Examples banner
        if examples:
            ey = Inches(6.15)
            _rect(sl, 0, ey, W, Inches(0.27), _TEAL)
            _txt(sl, 'EXAMPLES', Inches(0.4), ey,
                 Inches(1.5), Inches(0.27), sz=8, bold=True, color=_WHT)
            _txt(sl, '    Â·    '.join(str(e) for e in examples[:3]),
                 Inches(2.1), ey, Inches(11), Inches(0.27),
                 sz=9, italic=True, color=_WHT)
        if summary_txt:
            _txt(sl, f'â†³ {summary_txt}',
                 Inches(0.4), Inches(6.5 if examples else 6.3),
                 Inches(12.5), Inches(0.65), sz=11, italic=True, color=_GRY)

        # CO + Bloom footer
        footer = []
        if ks.bloom_level:
            footer.append(f"Bloom: {ks.bloom_level.value if hasattr(ks.bloom_level, 'value') else ks.bloom_level}")
        if ks.co_reference:
            footer.append(f"CO: {ks.co_reference}")
        if footer:
            _txt(sl, '   |   '.join(footer),
                 Inches(8.9), Inches(6.88), Inches(4.2), Inches(0.38), sz=9, color=_GRY)

        # Speaker notes
        notes = []
        if not is_dean:
            tn = (content.get('teaching_notes') or '').strip()
            if tn:
                notes.append(f'TEACHING NOTES:\n{tn}')
            if ks.speaker_notes:
                notes.append(f'SPEAKER NOTES:\n{ks.speaker_notes}')
        if footer:
            notes.append('  |  '.join(footer))
        if code_snippet:
            notes.append(f'CODE:\n{code_snippet}')
        if summary_txt:
            notes.append(f'STUDENT SUMMARY: {summary_txt}')
        if notes:
            sl.notes_slide.notes_text_frame.text = '\n\n'.join(notes)

    # â”€â”€ 4. TEACHING PLAN TABLE SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if tp:
        sl = prs.slides.add_slide(BLANK)
        _clear_placeholders(sl)
        _bg(sl, _WHT)
        _header(sl, 'Weekly Teaching Plan',
                subtitle=f'{course.code} â€” Unit {kit.unit_number}')
        n = min(len(tp), 10)
        tbl = sl.shapes.add_table(
            n + 1, 4, Inches(0.4), Inches(1.1), Inches(12.5), Inches(5.9)
        ).table
        _tbl_hdr(tbl, ('Wk', 'Topic', 'Objectives', 'CO Refs'),
                 (Inches(0.85), Inches(3.4), Inches(6.35), Inches(1.9)), _NAV)
        for ri, wk in enumerate(tp[:n], 1):
            _tbl_row(tbl, ri, [
                str(wk.get('week', ri)),
                str(wk.get('topic', ''))[:60],
                '  Â·  '.join(str(o) for o in (wk.get('objectives') or [])[:3])[:120],
                ', '.join(str(c2) for c2 in (wk.get('co_references') or [])),
            ], _LGRY)

    # â”€â”€ 5. SUMMARY SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    sl = prs.slides.add_slide(BLANK)
    _clear_placeholders(sl)
    _bg(sl, _WHT)
    _header(sl, 'Unit Summary â€” Key Takeaways',
            subtitle=f'{course.code} â€” Unit {kit.unit_number}', color=_GRN)

    summaries = [(ks.content or {}).get('student_summary') or ''
                 for ks in slides_sorted]
    summaries = [s.strip() for s in summaries if s.strip()]

    items = summaries[:9] if summaries else \
            [f"{getattr(co,'code','')}: {getattr(co,'description','')}"
             for co in effective_cos[:9]]
    if items:
        _txt(sl, 'What students should know after this unit:',
             Inches(0.5), Inches(1.1), Inches(12.3), Inches(0.38),
             sz=12, bold=True, color=_ACC)
        for i, s in enumerate(items):
            _txt(sl, f'âœ“  {s}', Inches(0.6), Inches(1.58 + i * 0.58),
                 Inches(12.3), Inches(0.55), sz=13, color=_TXT)

    # â”€â”€ 6. RESOURCES SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    resources = kit.resources or []
    if resources:
        sl = prs.slides.add_slide(BLANK)
        _clear_placeholders(sl)
        _bg(sl, _WHT)
        _header(sl, 'Teaching Resources & References',
                subtitle='Supplemental materials for faculty', color=_TEAL)
        ry2 = Inches(1.12)
        for res in resources[:10]:
            rtype = str(res.get('resource_type', '')).upper()[:12]
            title = str(res.get('title', ''))
            url   = str(res.get('url') or '')
            desc  = str(res.get('description') or '')
            _rect(sl, Inches(0.4), ry2, Inches(1.4), Inches(0.25), _ACC)
            _txt(sl, rtype, Inches(0.4), ry2, Inches(1.4), Inches(0.25),
                 sz=8, bold=True, color=_WHT, align=PP_ALIGN.CENTER)
            _txt(sl, title, Inches(1.9), ry2, Inches(11), Inches(0.28),
                 sz=12, bold=True, color=_TXT)
            detail = url or desc
            if detail:
                _txt(sl, detail[:110], Inches(1.9), ry2 + Inches(0.3),
                     Inches(11), Inches(0.25), sz=9, italic=True, color=_GRY)
                ry2 += Inches(0.68)
            else:
                ry2 += Inches(0.42)

    prs.save(buf)


# ---------------------------------------------------------------------------
# PPTX slide-body helper  (kept for PDF generation â€” not used in PPTX path)
# ---------------------------------------------------------------------------

def _fill_slide_body(tf, content: dict) -> None:
    """Render all H-34 SlideContent fields into a PPTX text-frame.

    teaching_notes is excluded here â€” it belongs in the notes pane only.
    Backward-compatible: missing or None fields are silently skipped.
    """
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    _ACCENT = RGBColor(0x44, 0x72, 0xC4)
    _GREEN  = RGBColor(0x21, 0x7A, 0x3C)
    _TEAL   = RGBColor(0x00, 0x7B, 0x8A)

    bullets            = content.get("bullets") or []
    key_concepts       = content.get("key_concepts") or []
    definitions        = content.get("definitions") or []
    examples           = content.get("examples") or []
    code_snippet       = (content.get("code_snippet") or "").strip()
    diagram_prompt     = (content.get("diagram_prompt") or "").strip()
    classroom_activity = (content.get("classroom_activity") or "").strip()
    student_summary    = (content.get("student_summary") or "").strip()

    tf.clear()
    _first = [True]

    def _para(text: str, *, level: int = 0, size: int = 18,
              bold: bool = False, italic: bool = False, color=None):
        if _first[0]:
            p = tf.paragraphs[0]
            _first[0] = False
        else:
            p = tf.add_paragraph()
        p.text  = text
        p.level = level
        for run in p.runs:
            run.font.size   = Pt(size)
            run.font.bold   = bold
            run.font.italic = italic
            if color is not None:
                run.font.color.rgb = color

    def _section(label: str, color=None):
        _para("", level=0, size=6)
        _para(label, level=0, size=13, bold=True, color=color or _ACCENT)

    for bullet in bullets:
        _para(bullet, level=0, size=18)

    if key_concepts:
        _section("Key Concepts")
        _para("  |  ".join(key_concepts), level=1, size=13, bold=True)

    if definitions:
        _section("Definitions", color=_GREEN)
        for defn in definitions:
            _para(f"â€¢ {defn}", level=1, size=14)

    if examples:
        _section("Examples", color=_TEAL)
        for ex in examples:
            _para(f"â€¢ {ex}", level=1, size=14)

    if code_snippet:
        _section("Code")
        for line in code_snippet.split("\n")[:20]:  # cap at 20 lines to prevent overflow
            _para(line or " ", level=1, size=11, italic=True)

    if diagram_prompt:
        _section("Diagram Prompt")
        _para(diagram_prompt, level=1, size=13)

    if classroom_activity:
        _section("Classroom Activity", color=_TEAL)
        _para(classroom_activity, level=1, size=13)

    if student_summary:
        _section("Student Summary")
        _para(student_summary, level=1, size=13)

# ---------------------------------------------------------------------------
# PDF generation (reportlab â€” slide handout + kit content)
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

    # â”€â”€ Cover â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    story.append(Paragraph(f"{course.code}: {course.title}", styles["Title"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Unit {kit.unit_number} â€” Teaching Kit", styles["Heading2"]
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

    # â”€â”€ Slides â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                story.append(Paragraph(f"â€¢ {bullet}", small))
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

    # â”€â”€ Weekly teaching plan â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    teaching_plan = kit.teaching_plan or []
    if teaching_plan:
        story.append(Paragraph("Weekly Teaching Plan", h1))
        story.append(Spacer(1, 0.3*cm))
        header = [["Week", "Topic", "Hours", "CO References"]]
        rows = []
        for week in teaching_plan:
            co_refs = ", ".join(week.get("co_references") or []) or "â€”"
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

    # â”€â”€ Quizlets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Assignments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Teaching Resources â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    resources = kit.resources or []
    if resources:
        story.append(Paragraph("Teaching Resources", h1))
        story.append(Spacer(1, 0.3*cm))
        for res in resources:
            rtype     = res.get("resource_type", "")
            title_str = res.get("title", "")
            url       = res.get("url")
            desc      = res.get("description")
            story.append(Paragraph(f"â€¢ [{rtype}] {title_str}", small))
            if desc:
                story.append(Paragraph(f"  {desc}", tiny))
            if url:
                story.append(Paragraph(f"  {url}", tiny))

    doc.build(story)


# ---------------------------------------------------------------------------
# Student handout PDF (sanitized â€” no speaker_notes, answer_key, model_answer, rubric)
# ---------------------------------------------------------------------------

def _generate_handout_pdf(buf, kit, course) -> None:
    """
    Produces a student-facing A4 PDF with a diagonal watermark.
    All faculty-sensitive fields are excluded:
      - KitSlide.speaker_notes
      - KitQuizlet.answer_key and answer_explanation
      - KitAssignment.model_answer and rubric
    Available to ADMIN, FACULTY, and DEAN roles.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    _BLUE   = colors.HexColor("#2E4057")
    _ACCENT = colors.HexColor("#4472C4")
    _ALT    = colors.HexColor("#EBF0FA")
    _WMARK  = colors.Color(0.80, 0.80, 0.80, alpha=0.30)

    watermark_text = f"STUDENT HANDOUT â€” {course.code}"

    def _draw_watermark(canv, doc):
        canv.saveState()
        canv.setFont("Helvetica", 36)
        canv.setFillColor(_WMARK)
        canv.translate(A4[0] / 2, A4[1] / 2)
        canv.rotate(45)
        canv.drawCentredString(0, 0, watermark_text)
        canv.restoreState()

    HO_GRID = TableStyle([
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
    ho_small = ParagraphStyle("ho_small", parent=styles["Normal"], fontSize=8,  leading=10)
    ho_tiny  = ParagraphStyle("ho_tiny",  parent=styles["Normal"], fontSize=7,  leading=9)
    ho_h1    = ParagraphStyle("ho_h1",    parent=styles["Heading1"], textColor=_BLUE)
    ho_h2    = ParagraphStyle("ho_h2",    parent=styles["Heading2"], textColor=_ACCENT)

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2*cm, bottomMargin=2*cm,
        leftMargin=2*cm, rightMargin=2*cm,
    )
    story = []

    # â”€â”€ Cover â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    story.append(Paragraph(f"{course.code}: {course.title}", styles["Title"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"Unit {kit.unit_number} â€” Student Handout", styles["Heading2"]))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=_BLUE))
    story.append(Spacer(1, 0.4*cm))

    meta_rows = [
        ["Course Code",  course.code],
        ["Course Title", course.title],
        ["Unit",         str(kit.unit_number)],
        ["Complexity",   kit.complexity_level.value],
    ]
    if kit.published_at:
        meta_rows.append(["Published At", kit.published_at.strftime("%Y-%m-%d")])

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

    # â”€â”€ Slides (content only â€” no speaker_notes) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    slides_sorted = sorted(kit.slides or [], key=lambda s: s.slide_number)
    if slides_sorted:
        story.append(Paragraph("Slides", ho_h1))
        story.append(Spacer(1, 0.3*cm))
        for kit_slide in slides_sorted:
            story.append(Paragraph(
                f"Slide {kit_slide.slide_number}: {kit_slide.title or '(untitled)'}",
                ho_h2,
            ))
            content      = kit_slide.content or {}
            bullets      = content.get("bullets") or []
            key_concepts = content.get("key_concepts") or []
            for bullet in bullets:
                story.append(Paragraph(f"â€¢ {bullet}", ho_small))
            if key_concepts:
                story.append(Paragraph(
                    "Key concepts: " + "  |  ".join(key_concepts), ho_tiny,
                ))
            footer_parts = []
            if kit_slide.bloom_level:
                footer_parts.append(f"Bloom: {kit_slide.bloom_level.value}")
            if kit_slide.co_reference:
                footer_parts.append(f"CO: {kit_slide.co_reference}")
            if footer_parts:
                story.append(Paragraph(" | ".join(footer_parts), ho_tiny))
            story.append(Spacer(1, 0.4*cm))
        story.append(PageBreak())

    # â”€â”€ Quizlets (questions + options only â€” no answer_key, no explanation) â”€â”€
    quizlets_sorted = sorted(kit.quizlets or [], key=lambda q: q.question_number)
    if quizlets_sorted:
        story.append(Paragraph("Quizlets", ho_h1))
        story.append(Spacer(1, 0.3*cm))
        for qz in quizlets_sorted:
            story.append(Paragraph(
                f"Q{qz.question_number}. [{qz.question_type.value}] {qz.question_text}",
                ho_small,
            ))
            for opt in (qz.options or []):
                if isinstance(opt, dict):
                    story.append(Paragraph(
                        f"  ({opt.get('label','?')}) {opt.get('text','')}", ho_tiny,
                    ))
            if qz.question_type.value == "SHORT_ANSWER":
                for _ in range(3):
                    story.append(Paragraph("_" * 80, ho_tiny))
            story.append(Spacer(1, 0.3*cm))
        story.append(PageBreak())

    # â”€â”€ Assignments (question text only â€” no model_answer, no rubric) â”€â”€â”€â”€â”€
    assignments_sorted = sorted(
        kit.assignments or [], key=lambda a: a.assignment_number
    )
    if assignments_sorted:
        story.append(Paragraph("Assignments", ho_h1))
        story.append(Spacer(1, 0.3*cm))
        for asn in assignments_sorted:
            story.append(Paragraph(
                f"Assignment {asn.assignment_number}: {asn.title}", ho_h2,
            ))
            story.append(Paragraph(
                f"Type: {asn.assignment_type.value}  |  "
                f"Complexity: {asn.complexity_level.value}",
                ho_tiny,
            ))
            story.append(Paragraph(asn.question_text, ho_small))
            story.append(Spacer(1, 0.5*cm))

    # â”€â”€ Teaching resources â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    resources = kit.resources or []
    if resources:
        story.append(Paragraph("Teaching Resources", ho_h1))
        story.append(Spacer(1, 0.3*cm))
        for res in resources:
            rtype     = res.get("resource_type", "")
            title_str = res.get("title", "")
            url       = res.get("url")
            desc      = res.get("description")
            story.append(Paragraph(f"â€¢ [{rtype}] {title_str}", ho_small))
            if desc:
                story.append(Paragraph(f"  {desc}", ho_tiny))
            if url:
                story.append(Paragraph(f"  {url}", ho_tiny))

    doc.build(story, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
