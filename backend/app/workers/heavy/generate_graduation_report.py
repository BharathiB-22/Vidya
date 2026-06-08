"""
Celery task — generate graduation audit report PDF.
"""
from __future__ import annotations

import io
from datetime import datetime

from celery import shared_task

from app.workers.celery_app import celery_app


@celery_app.task(
    name="app.workers.heavy.generate_graduation_report",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_graduation_report(self, audit_id: str) -> dict:
    """
    Generate a PDF summary report for a graduation audit.

    Layout sections:
      1. Header: institution name, batch name, program, academic year
      2. Summary table: total / eligible / provisional / not-eligible / ratified / deferred
      3. Candidate table: USN | Name | Program | Eligibility | Board Decision | Certificate
      4. Footer: generated timestamp, audit reference
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("reportlab is required for PDF generation") from exc

    import asyncio
    from uuid import UUID

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.modules.m11_sis.graduation_models import (
        SisGraduationAudit,
        SisGraduationCandidate,
    )

    async def _run() -> dict:
        async with AsyncSessionLocal() as db:
            audit = (await db.execute(
                select(SisGraduationAudit).where(
                    SisGraduationAudit.id == UUID(audit_id)
                )
            )).scalar_one_or_none()
            if not audit:
                return {"error": f"Audit {audit_id} not found"}

            candidates = (await db.execute(
                select(SisGraduationCandidate)
                .where(SisGraduationCandidate.audit_id == UUID(audit_id))
                .order_by(SisGraduationCandidate.student_name_snapshot)
            )).scalars().all()

            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                                    topMargin=2*cm, bottomMargin=2*cm)
            styles = getSampleStyleSheet()
            elements = []

            # Header
            elements.append(Paragraph("Graduation Audit Report", styles["Title"]))
            elements.append(Spacer(1, 0.3*cm))

            meta = [
                ["Batch",         audit.batch_name_snapshot or "-"],
                ["Program",       audit.program_name_snapshot or "-"],
                ["Academic Year", audit.academic_year_snapshot or "-"],
                ["Audit Status",  audit.status],
                ["Board Ref",     audit.board_resolution_ref or "-"],
                ["Generated",     datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
            ]
            meta_table = Table(meta, colWidths=[4*cm, 12*cm])
            meta_table.setStyle(TableStyle([
                ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE",   (0, 0), (-1, -1), 9),
                ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ]))
            elements.append(meta_table)
            elements.append(Spacer(1, 0.5*cm))

            # Summary
            elements.append(Paragraph("Summary", styles["Heading2"]))
            summary_data = [
                ["Total", "Eligible", "Provisional", "Not Eligible", "Ratified", "Deferred"],
                [
                    str(audit.total_candidates or 0),
                    str(audit.eligible_count or 0),
                    str(audit.provisional_count or 0),
                    str(audit.not_eligible_count or 0),
                    str(audit.ratified_count or 0),
                    str(audit.deferred_count or 0),
                ],
            ]
            summary_table = Table(summary_data, colWidths=[2.7*cm]*6)
            summary_table.setStyle(TableStyle([
                ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#2D4A7A")),
                ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
                ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE",    (0, 0), (-1, -1), 9),
                ("GRID",        (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(summary_table)
            elements.append(Spacer(1, 0.5*cm))

            # Candidate table
            elements.append(Paragraph("Candidates", styles["Heading2"]))
            headers = ["#", "USN", "Name", "Eligibility", "Board Decision", "Certificate"]
            rows = [headers]
            for i, c in enumerate(candidates, 1):
                rows.append([
                    str(i),
                    c.usn_snapshot or "-",
                    c.student_name_snapshot[:30],
                    c.eligibility_status,
                    c.board_status,
                    c.certificate_status,
                ])
            cand_table = Table(rows, colWidths=[1*cm, 3*cm, 6*cm, 3*cm, 3.5*cm, 3*cm])
            cand_table.setStyle(TableStyle([
                ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#2D4A7A")),
                ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
                ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",    (0, 0), (-1, -1), 8),
                ("GRID",        (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ]))
            elements.append(cand_table)

            doc.build(elements)
            pdf_bytes = buf.getvalue()

            # Store in S3
            s3_key = f"graduation/reports/{audit_id}/audit_report.pdf"
            try:
                from app.core.storage.service import StorageService
                await StorageService.upload_bytes(s3_key, pdf_bytes, content_type="application/pdf")
            except Exception:
                pass  # Storage upload failure is non-fatal for report generation

            return {"audit_id": audit_id, "s3_key": s3_key, "size_bytes": len(pdf_bytes)}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
