"""
M06 submission file text extractor.

Downloads a file from MinIO/S3 by object key and extracts plain text.
Supports: PDF (.pdf via pypdf), DOCX (.docx via python-docx), plain text (.txt).

Called synchronously from the Celery worker via asyncio executor.
Returns (text, None) on success or ("", error_message) on failure.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger("vidya.m06.text_extractor")


def _get_s3_client():
    import boto3
    from app.config import settings
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        use_ssl=settings.S3_USE_SSL,
    )


def _download_bytes(object_key: str) -> bytes:
    """Download raw bytes from S3/MinIO. Raises on failure."""
    from app.config import settings
    client = _get_s3_client()
    # object_key format: vidya-assets/{tenant_slug}/{entity_type}/{...}
    # Strip the bucket prefix to get the S3 key within the bucket.
    s3_key = object_key.removeprefix(f"{settings.S3_BUCKET}/")
    response = client.get_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    return response["Body"].read()


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
    return "\n".join(parts)


def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(para.text for para in doc.paragraphs)


def _extract_txt(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _extension(object_key: str) -> str:
    """Return lowercased file extension, e.g. '.pdf'."""
    filename = object_key.rsplit("/", 1)[-1]
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    return ""


def extract_text(object_key: str) -> tuple[str, str | None]:
    """
    Download and extract text from a storage object.

    Returns:
        (text, None)          — success
        ("", error_message)   — failure (caller decides how to handle)
    """
    ext = _extension(object_key)

    if ext not in (".pdf", ".docx", ".txt"):
        msg = f"Unsupported file type '{ext}' — manual review required."
        logger.warning("text_extractor: %s (key=%s)", msg, object_key)
        return "", msg

    try:
        data = _download_bytes(object_key)
    except Exception as exc:
        msg = f"Failed to download file from storage: {exc!s:.120}"
        logger.error("text_extractor download error: %s", exc)
        return "", msg

    try:
        if ext == ".pdf":
            text = _extract_pdf(data)
        elif ext == ".docx":
            text = _extract_docx(data)
        else:
            text = _extract_txt(data)
    except Exception as exc:
        msg = f"Text extraction failed ({ext}): {exc!s:.120}"
        logger.error("text_extractor parse error: %s", exc)
        return "", msg

    text = text.strip()
    if not text:
        return "", "File was empty or contained no extractable text."

    logger.info("text_extractor: extracted %d chars from %s", len(text), object_key)
    return text, None
