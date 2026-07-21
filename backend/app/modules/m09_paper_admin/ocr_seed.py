"""
M09.7 OCR Review Queue — Manual Testing Seed Data.

Five scan scenarios for LMS University validation testing.
Each scenario represents a different OCR quality problem path
that the review queue must handle.

Usage (call from a migration or management command):
    from app.modules.m09_paper_admin.ocr_seed import OCR_SEED_SCENARIOS
    for s in OCR_SEED_SCENARIOS:
        # s is a dict describing the scenario — use to insert test scripts.
        ...

Scenarios
---------
1. perfect_scan     — High quality; OCR confidence 0.97. Should NOT enter queue.
2. blurred_scan     — Blurred image; low OCR confidence 0.45 → LOW_CONFIDENCE queue.
3. rotated_scan     — ROTATED quality flag; medium confidence 0.72 → QUALITY_ISSUE queue.
4. partial_scan     — PARTIAL_SCAN flag + low confidence 0.31 → OCR_FAILURE priority.
5. ocr_failure      — OCR pipeline returned FAILED; no text extracted → OCR_FAILURE queue.
"""
from __future__ import annotations


OCR_SEED_SCENARIOS: list[dict] = [
    {
        "scenario_key": "perfect_scan",
        "label": "Scenario 1 — Perfect Scan",
        "description": (
            "Clear scan, high DPI, all pages readable. "
            "OCR confidence = 0.97. "
            "Expected: does NOT enter the review queue."
        ),
        "ocr_status": "COMPLETE",
        "ocr_confidence": 0.97,
        "ocr_text": (
            "Question 1: Describe the OSI model.\n"
            "Answer: The OSI model has seven layers: Physical, Data Link, Network, "
            "Transport, Session, Presentation, Application. Each layer serves a "
            "distinct function in the communication stack...\n\n"
            "Question 2: What is TCP/IP?\n"
            "Answer: TCP/IP is a suite of communication protocols used to connect "
            "network devices on the internet..."
        ),
        "scan_quality_flags": [],
        "ocr_quality_score": 98.0,
        "expected_queue_entry": False,
        "expected_priority_category": None,
    },
    {
        "scenario_key": "blurred_scan",
        "label": "Scenario 2 — Blurred Scan",
        "description": (
            "Scan is blurred (estimated DPI < 150). "
            "OCR confidence = 0.45, below the low threshold (0.60). "
            "Expected: enters queue as LOW_CONFIDENCE."
        ),
        "ocr_status": "COMPLETE",
        "ocr_confidence": 0.45,
        "ocr_text": (
            "Qu3st|on 1: Descr|b3 the OS| m0del.\n"
            "Answ3r: The 0SI m0del h@s sev3n l@yers: Phys|cal, D@ta L|nk, N3tw0rk..."
        ),
        "scan_quality_flags": [
            {
                "type": "LOW_DPI",
                "page": 1,
                "severity": "HIGH",
                "description": "Page 1 estimated resolution is 120 DPI (minimum: 150 DPI).",
            }
        ],
        "ocr_quality_score": 75.0,
        "expected_queue_entry": True,
        "expected_priority_category": "LOW_CONFIDENCE",
    },
    {
        "scenario_key": "rotated_scan",
        "label": "Scenario 3 — Rotated Scan",
        "description": (
            "Page 2 is rotated 90°. OCR confidence = 0.72 (between low 0.60 and medium 0.80). "
            "ROTATED flag severity = MEDIUM. "
            "Expected: enters queue as QUALITY_ISSUE due to HIGH severity flag on page 1 "
            "(LOW_DPI co-present). If only ROTATED: MEDIUM_CONFIDENCE."
        ),
        "ocr_status": "COMPLETE",
        "ocr_confidence": 0.72,
        "ocr_text": (
            "Question 1: What is cloud computing?\n"
            "Answer: Cloud computing delivers computing services over the internet...\n\n"
            "[Page 2 — rotated — OCR unable to extract text reliably]"
        ),
        "scan_quality_flags": [
            {
                "type": "ROTATED",
                "page": 2,
                "severity": "MEDIUM",
                "description": "Page 2 is rotated 90°. Re-scan or apply rotation correction.",
            },
            {
                "type": "LOW_DPI",
                "page": 2,
                "severity": "HIGH",
                "description": "Page 2 estimated resolution is 140 DPI.",
            },
        ],
        "ocr_quality_score": 60.0,
        "expected_queue_entry": True,
        "expected_priority_category": "QUALITY_ISSUE",
    },
    {
        "scenario_key": "partial_scan",
        "label": "Scenario 4 — Partial Scan",
        "description": (
            "Page 3 content stream is very short (truncated). "
            "OCR confidence = 0.31, far below the low threshold. "
            "Expected: OCR_FAILURE (ocr_confidence is None from pipeline) OR "
            "LOW_CONFIDENCE if confidence is present. Highest priority."
        ),
        "ocr_status": "COMPLETE",
        "ocr_confidence": 0.31,
        "ocr_text": (
            "Question 1: ...\n"
            "Answer: [incomplete — page 3 partially missing from scan]\n"
        ),
        "scan_quality_flags": [
            {
                "type": "PARTIAL_SCAN",
                "page": 3,
                "severity": "CRITICAL",
                "description": (
                    "Page 3 content stream is very short (42 bytes). "
                    "Possible truncated or low-quality scan."
                ),
            }
        ],
        "ocr_quality_score": 20.0,
        "expected_queue_entry": True,
        "expected_priority_category": "LOW_CONFIDENCE",
    },
    {
        "scenario_key": "ocr_failure",
        "label": "Scenario 5 — OCR Pipeline Failure",
        "description": (
            "OCR task crashed (e.g. corrupt PDF, unsupported encoding). "
            "ocr_status = FAILED, ocr_text = None, ocr_confidence = None. "
            "Expected: enters queue as OCR_FAILURE (priority_score = 4, highest)."
        ),
        "ocr_status": "FAILED",
        "ocr_confidence": None,
        "ocr_text": None,
        "scan_quality_flags": [
            {
                "type": "PARTIAL_SCAN",
                "page": 0,
                "severity": "CRITICAL",
                "description": "PDF could not be parsed: unexpected end of file at offset 4096.",
            }
        ],
        "ocr_quality_score": 0.0,
        "expected_queue_entry": True,
        "expected_priority_category": "OCR_FAILURE",
    },
]


def describe_scenarios() -> str:
    """Return a formatted summary of all seed scenarios for documentation."""
    lines = ["M09.7 OCR Review Queue — Seed Scenarios", "=" * 50, ""]
    for s in OCR_SEED_SCENARIOS:
        lines.append(f"  {s['label']}")
        lines.append(f"    {s['description']}")
        lines.append(f"    OCR Status:    {s['ocr_status']}")
        lines.append(f"    Confidence:    {s['ocr_confidence']}")
        lines.append(f"    Flags:         {len(s['scan_quality_flags'])} flag(s)")
        lines.append(f"    Queue Entry:   {s['expected_queue_entry']}")
        lines.append(f"    Category:      {s['expected_priority_category']}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe_scenarios())
