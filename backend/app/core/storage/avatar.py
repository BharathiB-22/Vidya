"""Profile picture (avatar) helpers.

Avatars are stored in the tenant's own object storage under
``vidya-assets/{tenant_slug}/avatar/{user_id}/{uuid}-photo.{ext}`` and the
*object key* — never a signed URL — is what lands in ``users.avatar_url``.
Signed URLs expire; an object key does not, so persisting the key is the only
way an uploaded picture keeps rendering a day later.

Read sites turn the stored key back into a viewable URL through
:func:`resolve_avatar_url`, which is a pure signing operation (no network I/O)
and therefore safe to call synchronously from a Pydantic validator.

Rows written before this module existed hold a full ``https://…`` URL; those
pass through untouched so existing users keep working.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

import boto3
from botocore.config import Config as BotoConfig

from app.config import settings

logger = logging.getLogger("vidya.storage.avatar")

# Browsers vary on what they report for JPEGs, and some send a bare
# application/octet-stream. Extension is the tiebreaker.
AVATAR_EXTENSIONS: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
AVATAR_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# Values already renderable by the browser (legacy rows, gravatar-style URLs).
_PASSTHROUGH = re.compile(r"^(https?://|data:image/|blob:|/)")

# Scope used for super-admin avatars: they belong to the platform, not to any
# one tenant, so they get their own top-level prefix alongside tenant slugs.
PLATFORM_SCOPE_SLUG = "platform"


def normalize_avatar_upload(filename: str | None, content_type: str | None) -> tuple[str, str]:
    """Resolve (content_type, extension) for an avatar upload, or raise ValueError.

    Accepts JPG / JPEG / PNG / WEBP. The declared content type wins when it is
    one we recognise; otherwise we fall back to the filename extension.
    """
    ext = ""
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[1].strip().lower()

    ct = (content_type or "").split(";")[0].strip().lower()

    if ct in AVATAR_CONTENT_TYPES:
        canonical_ext = ext if ext in AVATAR_EXTENSIONS else AVATAR_CONTENT_TYPES[ct]
        return AVATAR_EXTENSIONS[canonical_ext], canonical_ext
    if ext in AVATAR_EXTENSIONS:
        return AVATAR_EXTENSIONS[ext], ext

    raise ValueError("Profile picture must be a JPG, JPEG, PNG or WEBP image.")


@lru_cache(maxsize=1)
def _signing_client():
    """boto3 client used only for URL signing — cached because constructing one
    costs far more than the signature itself, and avatars are signed per row of
    every user list."""
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        use_ssl=settings.S3_USE_SSL,
        config=BotoConfig(signature_version="s3v4"),
    )


def resolve_avatar_url(value: str | None) -> str | None:
    """Turn a stored ``avatar_url`` into something an ``<img src>`` can load.

    Object keys are signed on the fly; already-renderable values (legacy rows)
    pass through; anything else becomes ``None`` so the UI falls back to initials
    rather than rendering a broken image.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if _PASSTHROUGH.match(value):
        return value
    if not value.startswith("vidya-assets/"):
        return None

    s3_key = value.removeprefix(f"{settings.S3_BUCKET}/")
    try:
        return _signing_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": s3_key},
            ExpiresIn=settings.PRESIGNED_URL_EXPIRY_MINUTES_GET * 60,
        )
    except Exception:  # signing must never take down a profile or user list
        logger.exception("Failed to sign avatar URL for key %s", value)
        return None
