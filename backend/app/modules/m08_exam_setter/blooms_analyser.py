"""
M08 Exam Setter — Bloom's compliance analyser.

Pure functions, no I/O. Input: list of question dicts with bloom_level and marks.
Output: actual distribution percentages and compliance report.

Bloom levels: REMEMBER, UNDERSTAND, APPLY, ANALYSE, EVALUATE, CREATE
"""
from __future__ import annotations

from dataclasses import dataclass, field


BLOOM_LEVELS = ("REMEMBER", "UNDERSTAND", "APPLY", "ANALYSE", "EVALUATE", "CREATE")


@dataclass
class BloomsViolation:
    level:         str
    requested_pct: float
    actual_pct:    float
    delta_pct:     float      # actual - requested (positive = exceeded, negative = deficit)


@dataclass
class ComplianceReport:
    requested_dist: dict[str, float]
    actual_dist:    dict[str, float]
    compliance_ok:  bool
    violations:     list[BloomsViolation] = field(default_factory=list)

    def to_violations_list(self) -> list[dict]:
        return [
            {
                "level":         v.level,
                "requested_pct": v.requested_pct,
                "actual_pct":    v.actual_pct,
                "delta_pct":     v.delta_pct,
            }
            for v in self.violations
        ]


def compute_actual_distribution(questions: list[dict]) -> dict[str, float]:
    """
    Compute actual Bloom's level distribution as percentages of total marks.

    Args:
        questions: list of dicts with keys {bloom_level: str, marks: float}

    Returns:
        dict mapping bloom level → percentage (0–100), rounded to 1 dp.
        If total_marks == 0, returns all zeros.
    """
    totals: dict[str, float] = {lvl: 0.0 for lvl in BLOOM_LEVELS}
    grand_total = 0.0

    for q in questions:
        lvl = (q.get("bloom_level") or "").upper()
        marks = float(q.get("marks") or 0)
        if lvl in totals:
            totals[lvl] += marks
        grand_total += marks

    if grand_total == 0:
        return {lvl: 0.0 for lvl in BLOOM_LEVELS}

    return {
        lvl: round((totals[lvl] / grand_total) * 100, 1)
        for lvl in BLOOM_LEVELS
    }


def check_compliance(
    requested: dict[str, float],
    actual: dict[str, float],
    tolerance: float = 5.0,
) -> ComplianceReport:
    """
    Compare requested vs actual Bloom's distribution.

    Args:
        requested: {bloom_level → percentage}. Missing levels treated as 0.
        actual:    {bloom_level → percentage}. Missing levels treated as 0.
        tolerance: acceptable ± deviation in percentage points (default 5.0).

    Returns:
        ComplianceReport with compliance_ok=True iff all levels within tolerance.
    """
    violations: list[BloomsViolation] = []

    req_upper = {k.upper(): v for k, v in requested.items()}
    act_upper = {k.upper(): v for k, v in actual.items()}
    req_norm = {lvl: float(req_upper.get(lvl, 0) or 0) for lvl in BLOOM_LEVELS}
    act_norm = {lvl: float(act_upper.get(lvl, 0) or 0) for lvl in BLOOM_LEVELS}

    for lvl in BLOOM_LEVELS:
        req_pct = req_norm[lvl]
        act_pct = act_norm[lvl]
        delta   = round(act_pct - req_pct, 1)
        if abs(delta) > tolerance:
            violations.append(
                BloomsViolation(
                    level=lvl,
                    requested_pct=req_pct,
                    actual_pct=act_pct,
                    delta_pct=delta,
                )
            )

    return ComplianceReport(
        requested_dist=req_norm,
        actual_dist=act_norm,
        compliance_ok=(len(violations) == 0),
        violations=violations,
    )
