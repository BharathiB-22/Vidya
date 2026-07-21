"""
Celery task — generate graduation certificate PDF.

Certificate layout:
  1. Institution header (name, logo placeholder)
  2. Certificate title: "Bachelor / Master of <Degree>"
  3. Conferred upon: <student name> (USN)
  4. Programme, batch, graduation year
  5. QR code for public verification (verify/certificate/{number})
  6. Provisional advisory label (if is_provisional)
  7. Footer: certificate number, issued date, Registrar placeholder signature block
"""
from __future__ import annotations

import io

from app.database import tenant_schema_scope
from app.workers.celery_app import celery_app

_async_engine = None


def _get_async_engine():
    """Worker-owned engine, mirroring every other heavy task.

    Not `AsyncSessionLocal`: that is the API's request engine, and this task runs
    its coroutine on a fresh event loop each time. A pooled asyncpg connection
    belongs to the loop that created it, so reusing the request engine here raises
    "Future attached to a different loop" — hence NullPool.
    """
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        from app.config import settings
        from app.database import bind_tenant_search_path
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        # Re-apply the schema at the START OF EVERY TRANSACTION, not once per
        # session. This task commits the pdf_s3_key mid-run; without a per-BEGIN
        # SET LOCAL everything after that commit would run with search_path =
        # public, and a pooled connection could arrive carrying ANOTHER tenant's.
        bind_tenant_search_path(_async_engine)
    return _async_engine


@celery_app.task(
    name="app.workers.heavy.generate_graduation_certificate",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_graduation_certificate(self, schema_name: str, cert_id: str) -> dict:
    """`schema_name` is the tenant this certificate belongs to. It is required,
    not optional: sis_graduation_certificates is a tenant-schema table, and
    without it the task would read `public` and find nothing."""
    try:
        from reportlab.graphics import renderPDF
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("reportlab is required for certificate generation") from exc

    import asyncio
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy import select

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.m11_sis.graduation_models import SisGraduationCertificate

    engine = _get_async_engine()

    async def _run() -> dict:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            cert = (await db.execute(
                select(SisGraduationCertificate).where(
                    SisGraduationCertificate.id == UUID(cert_id)
                )
            )).scalar_one_or_none()
            if not cert:
                return {"error": f"Certificate {cert_id} not found"}

            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=A4,
                rightMargin=3*cm,
                leftMargin=3*cm,
                topMargin=3*cm,
                bottomMargin=3*cm,
            )

            styles = getSampleStyleSheet()
            centre_bold = ParagraphStyle(
                "CentreBold",
                parent=styles["Normal"],
                alignment=1,
                fontName="Helvetica-Bold",
            )
            centre = ParagraphStyle(
                "Centre",
                parent=styles["Normal"],
                alignment=1,
                fontName="Helvetica",
            )
            elements = []

            # Institution header
            elements.append(Paragraph(
                cert.school_name_snapshot or "Institution",
                ParagraphStyle("Inst", parent=centre_bold, fontSize=16),
            ))
            elements.append(Spacer(1, 0.2*cm))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2D4A7A")))
            elements.append(Spacer(1, 1.5*cm))

            # Certificate title
            degree_title = cert.degree_title_snapshot or cert.program_name_snapshot or "Degree"
            elements.append(Paragraph(
                "This is to certify that",
                ParagraphStyle("Subtitle", parent=centre, fontSize=11),
            ))
            elements.append(Spacer(1, 0.8*cm))

            # Student name
            elements.append(Paragraph(
                cert.student_name_snapshot.upper(),
                ParagraphStyle("StudentName", parent=centre_bold, fontSize=22),
            ))
            if cert.usn_snapshot:
                elements.append(Paragraph(
                    f"USN: {cert.usn_snapshot}",
                    ParagraphStyle("USN", parent=centre, fontSize=10, textColor=colors.grey),
                ))
            elements.append(Spacer(1, 0.8*cm))

            elements.append(Paragraph(
                "has successfully completed the requirements for the degree of",
                ParagraphStyle("Conferred", parent=centre, fontSize=11),
            ))
            elements.append(Spacer(1, 0.5*cm))
            elements.append(Paragraph(
                degree_title,
                ParagraphStyle("Degree", parent=centre_bold, fontSize=16,
                               textColor=colors.HexColor("#2D4A7A")),
            ))
            elements.append(Spacer(1, 0.5*cm))

            if cert.program_name_snapshot:
                elements.append(Paragraph(
                    f"in {cert.program_name_snapshot}",
                    ParagraphStyle("Program", parent=centre, fontSize=12),
                ))
            elements.append(Spacer(1, 1*cm))

            # Details table
            issued_date = cert.issued_at.strftime("%d %B %Y") if cert.issued_at else "-"
            details_data = [
                ["Batch",            cert.batch_name_snapshot or "-"],
                ["Graduation Year",  str(cert.graduation_year)],
                ["Date of Issue",    issued_date],
                ["Certificate No.",  cert.certificate_number or "-"],
            ]
            details_table = Table(details_data, colWidths=[5*cm, 10*cm])
            details_table.setStyle(TableStyle([
                ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE",   (0, 0), (-1, -1), 10),
                ("ALIGN",      (0, 0), (0, -1), "RIGHT"),
                ("ALIGN",      (1, 0), (1, -1), "LEFT"),
                ("LINEBELOW",  (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]))
            elements.append(details_table)
            elements.append(Spacer(1, 1.5*cm))

            # QR code for public verification
            verify_url = f"https://verify.vidya.app/verify/certificate/{cert.certificate_number}"
            qr = QrCodeWidget(verify_url)
            qr_w, qr_h = 3.5*cm, 3.5*cm
            drawing = Drawing(qr_w, qr_h)
            drawing.add(qr)

            qr_data = [[
                renderPDF.drawToString(drawing),
                Paragraph(
                    f"Scan to verify certificate authenticity<br/>"
                    f"<font size=8>{cert.certificate_number}</font>",
                    ParagraphStyle("QRLabel", parent=centre, fontSize=9),
                ),
            ]]
            qr_table = Table(qr_data, colWidths=[4.5*cm, 10*cm])
            elements.append(qr_table)
            elements.append(Spacer(1, 1*cm))

            # Provisional advisory
            if cert.is_provisional:
                elements.append(HRFlowable(width="100%", thickness=1, color=colors.orange))
                elements.append(Spacer(1, 0.2*cm))
                elements.append(Paragraph(
                    "PROVISIONAL CERTIFICATE — Subject to clearance of pending requirements. "
                    "Full graduation certificate will be issued upon confirmation by the Registrar.",
                    ParagraphStyle("Provisional", parent=centre, fontSize=9,
                                   textColor=colors.orangered),
                ))
                elements.append(Spacer(1, 0.3*cm))
                elements.append(HRFlowable(width="100%", thickness=1, color=colors.orange))

            elements.append(Spacer(1, 1.5*cm))

            # Signature block (placeholder)
            sig_data = [[
                Paragraph("_______________<br/>Registrar", centre),
                Paragraph("_______________<br/>Dean / Board Chairperson", centre),
            ]]
            sig_table = Table(sig_data, colWidths=[7.5*cm, 7.5*cm])
            elements.append(sig_table)

            doc.build(elements)
            pdf_bytes = buf.getvalue()

            # Store in S3
            s3_key = f"graduation/certificates/{cert.student_id}/{cert_id}.pdf"
            try:
                from app.core.storage.service import StorageService
                await StorageService.upload_bytes(s3_key, pdf_bytes, content_type="application/pdf")

                # Update certificate record with S3 key and timestamp
                from datetime import timezone
                from sqlalchemy import update
                from app.modules.m11_sis.graduation_models import SisGraduationCertificate as Cert
                await db.execute(
                    update(Cert)
                    .where(Cert.id == UUID(cert_id))
                    .values(
                        pdf_s3_key=s3_key,
                        pdf_generated_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
            except Exception:
                pass  # S3 failure is non-fatal

            return {
                "cert_id":    cert_id,
                "s3_key":     s3_key,
                "size_bytes": len(pdf_bytes),
                "certificate_number": cert.certificate_number,
            }

    # Which tenant every transaction in this task belongs to. Held for the whole
    # run and dropped at the end of it: a worker process is long-lived and serves
    # every tenant in turn, and a schema left set is one the next task inherits.
    with tenant_schema_scope(schema_name):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
