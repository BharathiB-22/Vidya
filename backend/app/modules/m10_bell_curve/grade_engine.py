"""
M10 Bell Curve Normaliser — Grade calculation engine.

Pure computation — no DB access, no side effects.

Grade scale: Indian 10-point UGC scheme (default).
  S  ≥ 90 %  → 10 grade points  (Outstanding)
  A  ≥ 80 %  →  9 grade points  (Excellent)
  B  ≥ 70 %  →  8 grade points  (Very Good)
  C  ≥ 60 %  →  7 grade points  (Good)
  D  ≥ 50 %  →  6 grade points  (Above Average)
  P  ≥ pass  →  5 grade points  (Pass)        pass_pct default = 40 %
  F  < pass  →  0 grade points  (Fail)

Pass threshold is configurable so institutions can override (35 %, 45 %, 50 %, …).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Grade scale — ordered from highest to lowest
# ---------------------------------------------------------------------------

_GRADE_SCALE: list[tuple[float, str, float]] = [
    (90.0, "S", 10.0),
    (80.0, "A",  9.0),
    (70.0, "B",  8.0),
    (60.0, "C",  7.0),
    (50.0, "D",  6.0),
]

_PASS_GRADE        = ("P", 5.0)
_FAIL_GRADE        = ("F", 0.0)
DEFAULT_PASS_PCT   = 40.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_grade(
    normalised_score: float,
    max_marks: float,
    pass_pct: float = DEFAULT_PASS_PCT,
) -> tuple[float, str, float, bool]:
    """
    Compute percentage, grade letter, grade point, and pass/fail for one student.

    Args:
        normalised_score: the student's score after bell-curve normalisation.
        max_marks:        maximum possible marks for the exam.
        pass_pct:         minimum percentage to pass (default 40.0).

    Returns:
        (pct, grade_letter, grade_point, is_pass)
        pct          — rounded to 1 decimal place; clamped to [0.0, 100.0]
        grade_letter — one of S | A | B | C | D | P | F
        grade_point  — 0.0 – 10.0
        is_pass      — True when pct >= pass_pct
    """
    if max_marks <= 0:
        return (0.0, _FAIL_GRADE[0], _FAIL_GRADE[1], False)

    raw_pct = normalised_score / max_marks * 100.0
    pct     = round(max(0.0, min(100.0, raw_pct)), 1)
    is_pass = pct >= pass_pct

    for threshold, letter, points in _GRADE_SCALE:
        if pct >= threshold:
            return (pct, letter, points, is_pass)

    if is_pass:
        return (pct, _PASS_GRADE[0], _PASS_GRADE[1], True)

    return (pct, _FAIL_GRADE[0], _FAIL_GRADE[1], False)


def grade_distribution(
    rows: list[dict],
    pass_pct: float = DEFAULT_PASS_PCT,
) -> dict[str, int]:
    """
    Aggregate grade counts across a list of score rows.

    rows: each dict must have 'normalised_score' and 'max_marks'.
    Returns: {grade_letter: count} for every grade that appears.
    """
    counts: dict[str, int] = {}
    for row in rows:
        _, letter, _, _ = compute_grade(
            float(row["normalised_score"]),
            float(row["max_marks"]),
            pass_pct=pass_pct,
        )
        counts[letter] = counts.get(letter, 0) + 1
    return counts
