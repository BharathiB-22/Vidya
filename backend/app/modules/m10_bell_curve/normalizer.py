"""
M10 Bell Curve Normaliser — Normalisation engine.

Functions:
  apply_normalisation()   — compute normalised_score for each student row
  preview_normalisation() — same computation but returns a preview dict (no DB write)

Supported methods:
  LINEAR_SCALE   — score_new = min(score * scale_factor, max_marks)
  PERCENTILE_MAP — normalised = percentile_rank/100 * target_max
  BOUNDARY_SHIFT — raw scores unchanged; affects grade boundary assignment only
                   (normalised_score == raw_score; boundary metadata stored in params)
  NONE           — normalised_score == raw_score
  CUSTOM         — Board-supplied deltas [{student_roll_ref, delta}]

Safety invariants enforced here:
  - normalised_score is always clamped to [0, max_marks]
  - max_marks is never exceeded
  - No DB access in this module — pure computation only
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# apply_normalisation
# ---------------------------------------------------------------------------

def apply_normalisation(
    ledger_rows: list[dict],
    method:      str,
    params:      dict[str, Any],
) -> list[dict]:
    """
    Compute normalised_score for each ledger row.

    ledger_rows: [{student_user_id, student_roll_ref, total_marks, max_marks, ...}]
    Returns:     [{student_user_id, student_roll_ref, raw_score, normalised_score, max_marks}]
    """
    if not ledger_rows:
        return []

    max_marks = float(ledger_rows[0]["max_marks"])
    scores    = [float(r["total_marks"]) for r in ledger_rows]

    normalised = _compute_normalised(scores, max_marks, method, params)

    return [
        {
            "student_user_id":  row.get("student_user_id"),
            "student_roll_ref": row.get("student_roll_ref"),
            "raw_score":        float(row["total_marks"]),
            "normalised_score": normalised[i],
            "max_marks":        max_marks,
        }
        for i, row in enumerate(ledger_rows)
    ]


# ---------------------------------------------------------------------------
# preview_normalisation
# ---------------------------------------------------------------------------

def preview_normalisation(
    ledger_rows: list[dict],
    method:      str,
    params:      dict[str, Any],
) -> dict[str, Any]:
    """
    Compute projected outcome without writing to DB.
    Returns a preview dict matching PreviewNormalisationResponse schema.
    """
    import numpy as np
    from scipy import stats as sp_stats

    rows = apply_normalisation(ledger_rows, method, params)
    if not rows:
        return {
            "method": method,
            "params": params,
            "projected_stats": _empty_stats(),
            "score_deltas": [],
        }

    normalised_arr = np.array([r["normalised_score"] for r in rows], dtype=float)
    n = len(normalised_arr)

    projected = {
        "mean":     round(float(np.mean(normalised_arr)), 4),
        "std":      round(float(np.std(normalised_arr, ddof=1)) if n > 1 else 0.0, 4),
        "median":   round(float(np.median(normalised_arr)), 4),
        "min":      round(float(np.min(normalised_arr)), 4),
        "max":      round(float(np.max(normalised_arr)), 4),
        "skewness": round(float(sp_stats.skew(normalised_arr, bias=False)) if n > 2 else 0.0, 4),
    }

    deltas = [
        {
            "student_roll_ref": r["student_roll_ref"],
            "raw":              r["raw_score"],
            "normalised":       r["normalised_score"],
            "delta":            round(r["normalised_score"] - r["raw_score"], 2),
        }
        for r in rows
    ]

    return {
        "method":          method,
        "params":          params,
        "projected_stats": projected,
        "score_deltas":    deltas,
    }


# ---------------------------------------------------------------------------
# Internal computation
# ---------------------------------------------------------------------------

def _compute_normalised(
    scores:    list[float],
    max_marks: float,
    method:    str,
    params:    dict[str, Any],
) -> list[float]:
    """Route to the correct normalisation function and clamp output."""
    if method == "LINEAR_SCALE":
        result = _linear_scale(scores, max_marks, params)
    elif method == "PERCENTILE_MAP":
        result = _percentile_map(scores, max_marks, params)
    elif method == "BOUNDARY_SHIFT":
        result = scores[:]          # raw scores unchanged; boundary shifts only
    elif method == "NONE":
        result = scores[:]
    elif method == "CUSTOM":
        result = _custom(scores, params)
    else:
        result = scores[:]

    # Clamp to [0, max_marks]
    return [max(0.0, min(max_marks, round(s, 2))) for s in result]


def _linear_scale(
    scores:    list[float],
    max_marks: float,
    params:    dict[str, Any],
) -> list[float]:
    """score_new = score * scale_factor; capped at max_marks."""
    factor = float(params.get("scale_factor", 1.0))
    if factor <= 0:
        factor = 1.0
    return [s * factor for s in scores]


def _percentile_map(
    scores:    list[float],
    max_marks: float,
    params:    dict[str, Any],
) -> list[float]:
    """
    Map each score to its percentile rank, then scale to target_max.
    normalised = (percentile_rank / 100) * target_max
    """
    import numpy as np

    target_max = float(params.get("target_max", max_marks))
    if not scores:
        return []

    arr = np.array(scores, dtype=float)
    n   = len(arr)
    # Percentile rank for each score (0-100)
    ranks = [
        (sum(s2 <= s for s2 in scores) / n) * 100.0
        for s in scores
    ]
    return [(r / 100.0) * target_max for r in ranks]


def _custom(scores: list[float], params: dict[str, Any]) -> list[float]:
    """
    Apply Board-specified per-student deltas by index position.
    params: {adjustments: [{student_roll_ref, delta}]}
    Delta is applied positionally; unmatched students get delta=0.
    """
    adjustments = params.get("adjustments", [])
    delta_list  = [float(a.get("delta", 0)) for a in adjustments]
    result = []
    for i, s in enumerate(scores):
        delta = delta_list[i] if i < len(delta_list) else 0.0
        result.append(s + delta)
    return result


def _empty_stats() -> dict:
    return {
        "mean": 0.0, "std": 0.0, "median": 0.0,
        "min": 0.0, "max": 0.0, "skewness": 0.0,
    }
