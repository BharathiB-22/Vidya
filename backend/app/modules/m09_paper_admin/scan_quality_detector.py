"""
M09 Scan Quality Detector — PDF quality analysis (no AI, no OCR, no DB).

Public API:
    detect_scan_quality(pdf_bytes, *, expected_page_count=None) -> ScanQualityResult

Flag types (match scanned_scripts.scan_quality_flags JSONB schema):
    Each flag: {type, page, severity, description}
    type values:
        BLANK_PAGE    — page with negligible content stream
        LOW_DPI       — scan resolution estimated below 150 DPI
        ROTATED       — page rotated 90° or 270° (landscape when portrait expected)
        UPSIDE_DOWN   — page rotated 180°
        DUPLICATE     — identical content on two or more pages within this script
        PARTIAL_SCAN  — content present but stream suspiciously short, or PDF unreadable
        MISSING_PAGES — actual page count < expected_page_count

Scoring:
    Start at 100. Deduct per flag: CRITICAL=40, HIGH=25, MEDIUM=15, LOW=5.
    quality_score = max(0, 100 - total_deductions).
    passed = quality_score >= QUALITY_PASS_THRESHOLD (60).

Human-gate invariant:
    This module performs NO database access, NO S3 access, NO AI calls.
    All analysis is pure-Python on supplied PDF bytes.
    Detection that requires rendering (pixel-level blank check, precise DPI)
    is deferred to the OCR pipeline (STEP-03).
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import logging

logger = logging.getLogger("vidya.m09.scan_quality_detector")

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Content stream smaller than this (bytes) → BLANK_PAGE
_BLANK_CONTENT_THRESHOLD = 150

# Non-blank content stream smaller than this → PARTIAL_SCAN
_PARTIAL_CONTENT_THRESHOLD = 600

# DPI estimate below this (when detectable) → LOW_DPI
_MIN_DPI_THRESHOLD = 150

# quality_score below this → passed=False
QUALITY_PASS_THRESHOLD = 60

# Deductions per severity level
_SEVERITY_DEDUCTIONS: dict[str, int] = {
    "CRITICAL": 40,
    "HIGH":     25,
    "MEDIUM":   15,
    "LOW":       5,
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class QualityFlag:
    type:        str   # BLANK_PAGE | LOW_DPI | ROTATED | UPSIDE_DOWN | DUPLICATE | PARTIAL_SCAN | MISSING_PAGES
    page:        int   # 1-based page number; 0 = whole-document issue
    severity:    str   # CRITICAL | HIGH | MEDIUM | LOW
    description: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class ScanQualityResult:
    quality_score: float           # 0–100
    flags:         list[QualityFlag]
    passed:        bool
    page_count:    int             # actual PDF page count (0 if PDF unparseable)


# ---------------------------------------------------------------------------
# Low-level page helpers (separated for testability)
# ---------------------------------------------------------------------------

def _get_content_bytes(page) -> bytes:
    """Extract raw content stream bytes from a pypdf page object."""
    try:
        contents = page.get_contents()
        if contents is None:
            return b""
        if isinstance(contents, list):
            return b"".join(
                c.get_data() for c in contents if hasattr(c, "get_data")
            )
        return contents.get_data() if hasattr(contents, "get_data") else b""
    except Exception:
        return b""


def _get_rotation(page) -> int:
    """Return page rotation in degrees (0, 90, 180, or 270)."""
    try:
        return int(page.rotation or 0)
    except Exception:
        return 0


def _page_content_hash(content_bytes: bytes) -> str:
    """SHA-256 of page content bytes — used for duplicate detection."""
    return hashlib.sha256(content_bytes).hexdigest()


def _estimate_dpi(page) -> float | None:
    """
    Estimate scan DPI from the first image XObject on the page.
    Returns None if no images present or estimation fails.
    Formula: dpi = (image_pixel_width / page_width_points) * 72
    """
    try:
        mediabox = page.mediabox
        page_w = float(mediabox.width)
        page_h = float(mediabox.height)
        if page_w <= 0 or page_h <= 0:
            return None

        images = page.images
        if not images:
            return None

        img = images[0]
        img_w = getattr(img, "width",  None)
        img_h = getattr(img, "height", None)
        if not img_w or not img_h:
            return None

        dpi_x = (float(img_w) / page_w) * 72
        dpi_y = (float(img_h) / page_h) * 72
        return min(dpi_x, dpi_y)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------

def _compute_score(flags: list[QualityFlag]) -> tuple[float, bool]:
    """Return (quality_score, passed) from the accumulated flags.
    Score must be strictly above QUALITY_PASS_THRESHOLD to pass (borderline = fail).
    """
    total_deduction = sum(_SEVERITY_DEDUCTIONS.get(f.severity, 0) for f in flags)
    score = max(0.0, float(100 - total_deduction))
    return score, score > QUALITY_PASS_THRESHOLD


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_scan_quality(
    pdf_bytes: bytes,
    *,
    expected_page_count: int | None = None,
) -> ScanQualityResult:
    """
    Analyse a scanned answer script PDF for quality issues.

    pdf_bytes:           Raw bytes of the uploaded PDF.
    expected_page_count: If provided, a MISSING_PAGES flag is raised when
                         the actual page count is less than this value.

    Returns ScanQualityResult. Never raises — all errors produce a
    quality-failed result so the Celery worker can always store an outcome.
    """
    flags: list[QualityFlag] = []

    # ------------------------------------------------------------------
    # Guard: empty or missing bytes
    # ------------------------------------------------------------------
    if not pdf_bytes:
        flags.append(QualityFlag(
            type="PARTIAL_SCAN",
            page=0,
            severity="CRITICAL",
            description="No PDF data provided; scan file is empty or unavailable.",
        ))
        score, passed = _compute_score(flags)
        return ScanQualityResult(quality_score=score, flags=flags, passed=passed, page_count=0)

    # ------------------------------------------------------------------
    # Parse PDF
    # ------------------------------------------------------------------
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        pages  = reader.pages
    except Exception as exc:
        logger.warning("PDF parse error during quality check: %s", exc)
        flags.append(QualityFlag(
            type="PARTIAL_SCAN",
            page=0,
            severity="CRITICAL",
            description=f"PDF could not be parsed: {str(exc)[:200]}",
        ))
        score, passed = _compute_score(flags)
        return ScanQualityResult(quality_score=score, flags=flags, passed=passed, page_count=0)

    actual_page_count = len(pages)

    # ------------------------------------------------------------------
    # Check: MISSING_PAGES (document-level)
    # ------------------------------------------------------------------
    if expected_page_count and actual_page_count < expected_page_count:
        flags.append(QualityFlag(
            type="MISSING_PAGES",
            page=0,
            severity="HIGH",
            description=(
                f"Expected {expected_page_count} pages but found {actual_page_count}. "
                "Possible incomplete upload or multi-file split."
            ),
        ))

    # ------------------------------------------------------------------
    # Per-page checks
    # ------------------------------------------------------------------
    seen_hashes: dict[str, int] = {}  # content_hash → first page number (1-based)

    for page_no, page in enumerate(pages, start=1):
        try:
            content_bytes = _get_content_bytes(page)
            content_len   = len(content_bytes)
            rotation      = _get_rotation(page)
            page_hash     = _page_content_hash(content_bytes)

            # Check: BLANK_PAGE
            if content_len < _BLANK_CONTENT_THRESHOLD:
                flags.append(QualityFlag(
                    type="BLANK_PAGE",
                    page=page_no,
                    severity="HIGH",
                    description=(
                        f"Page {page_no} appears blank "
                        f"(content stream: {content_len} bytes). "
                        "Re-scan or verify the page was not skipped."
                    ),
                ))
            # Check: PARTIAL_SCAN (non-blank but suspiciously sparse)
            elif content_len < _PARTIAL_CONTENT_THRESHOLD:
                flags.append(QualityFlag(
                    type="PARTIAL_SCAN",
                    page=page_no,
                    severity="MEDIUM",
                    description=(
                        f"Page {page_no} content stream is very short "
                        f"({content_len} bytes). Possible truncated or low-quality scan."
                    ),
                ))

            # Check: ROTATED (landscape orientation when portrait expected)
            if rotation in (90, 270):
                flags.append(QualityFlag(
                    type="ROTATED",
                    page=page_no,
                    severity="MEDIUM",
                    description=(
                        f"Page {page_no} is rotated {rotation}°. "
                        "Re-scan or apply rotation correction before processing."
                    ),
                ))

            # Check: UPSIDE_DOWN
            if rotation == 180:
                flags.append(QualityFlag(
                    type="UPSIDE_DOWN",
                    page=page_no,
                    severity="MEDIUM",
                    description=(
                        f"Page {page_no} is upside-down (rotated 180°). "
                        "Re-scan or apply rotation correction."
                    ),
                ))

            # Check: DUPLICATE (same content hash as an earlier page)
            if page_hash in seen_hashes:
                first = seen_hashes[page_hash]
                flags.append(QualityFlag(
                    type="DUPLICATE",
                    page=page_no,
                    severity="HIGH",
                    description=(
                        f"Page {page_no} appears identical to page {first}. "
                        "Possible scanner feed error or accidental duplicate."
                    ),
                ))
            else:
                seen_hashes[page_hash] = page_no

            # Check: LOW_DPI (only when image DPI is estimable)
            dpi = _estimate_dpi(page)
            if dpi is not None and dpi < _MIN_DPI_THRESHOLD:
                flags.append(QualityFlag(
                    type="LOW_DPI",
                    page=page_no,
                    severity="HIGH",
                    description=(
                        f"Page {page_no} estimated resolution is {dpi:.0f} DPI "
                        f"(minimum: {_MIN_DPI_THRESHOLD} DPI). Re-scan at higher resolution."
                    ),
                ))

        except Exception as exc:
            logger.warning("Page %d quality check error: %s", page_no, exc)

    # ------------------------------------------------------------------
    # Compute overall quality score
    # ------------------------------------------------------------------
    score, passed = _compute_score(flags)
    return ScanQualityResult(
        quality_score=score,
        flags=flags,
        passed=passed,
        page_count=actual_page_count,
    )
