"""
M10 Bell Curve Normaliser — Statistical analysis engine.

Functions:
  compute_stats()          — mean, std, median, skewness, kurtosis, Q1/Q3, histogram
  detect_anomalies()       — zero inflation, ceiling effect, bimodality (BC), excessive skew
  cross_evaluator_stats()  — per-evaluator mean/std/count with z-score outlier flag
  suggest_normalisation()  — choose the best normalization method + params

Dependencies: numpy (already installed 2.4.4 as transitive dep), scipy (added to pyproject.toml)

Bimodality detection uses the Bimodality Coefficient (BC):
  BC = (skewness^2 + 1) / (kurtosis_excess + 3*(n-1)^2/((n-2)*(n-3)))
  BC > 0.555 is treated as a bimodal indicator.
  BC is used as a lightweight heuristic indicator for multimodal distributions
  and avoids unstable native dependencies on Windows/Python 3.12.

PRD thresholds:
  zero_inflation  : count(score==0) / total > 0.15
  ceiling_effect  : count(score==max) / total > 0.20
  bimodal         : BC > 0.555
  excessive_skew  : |skewness| > 1.5
  evaluator_outlier: |z-score| > 2.0
"""
from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Anomaly type constants
# ---------------------------------------------------------------------------

ZERO_INFLATION  = "ZERO_INFLATION"
CEILING_EFFECT  = "CEILING_EFFECT"
BIMODAL         = "BIMODAL"
EXCESSIVE_SKEW  = "EXCESSIVE_SKEW"

SEVERITY_WARNING  = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"

# PRD thresholds
_ZERO_INFLATION_THRESH   = 0.15
_CEILING_EFFECT_THRESH   = 0.20
_BC_BIMODAL_THRESH       = 0.555
_SKEW_THRESH             = 1.5
_EVALUATOR_ZSCORE_THRESH = 2.0
_HISTOGRAM_BINS          = 20


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------

def compute_stats(scores: list[float], max_possible: float) -> dict[str, Any]:
    """
    Compute descriptive statistics for a list of scores.

    Returns a dict matching RawStats schema:
      {mean, std, median, min, max, skewness, kurtosis, q1, q3, histogram[]}
    """
    import numpy as np
    from scipy import stats as sp_stats

    if not scores:
        return {
            "mean": 0.0, "std": 0.0, "median": 0.0,
            "min": 0.0, "max": 0.0, "skewness": 0.0,
            "kurtosis": 0.0, "q1": 0.0, "q3": 0.0,
            "histogram": [],
        }

    arr = np.array(scores, dtype=float)
    n   = len(arr)

    mean    = float(np.mean(arr))
    std     = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    median  = float(np.median(arr))
    q1      = float(np.percentile(arr, 25))
    q3      = float(np.percentile(arr, 75))
    minimum = float(np.min(arr))
    maximum = float(np.max(arr))

    # scipy skewness/kurtosis (excess kurtosis, bias=False for sample correction)
    skewness = float(sp_stats.skew(arr, bias=False)) if n > 2 else 0.0
    kurtosis = float(sp_stats.kurtosis(arr, bias=False)) if n > 3 else 0.0

    # Histogram — fixed range [0, max_possible] for comparability
    bin_edges = np.linspace(0.0, max(max_possible, maximum), _HISTOGRAM_BINS + 1)
    counts, edges = np.histogram(arr, bins=bin_edges)
    histogram = [
        {
            "bin_start": round(float(edges[i]), 2),
            "bin_end":   round(float(edges[i + 1]), 2),
            "count":     int(counts[i]),
        }
        for i in range(len(counts))
    ]

    return {
        "mean":      round(mean, 4),
        "std":       round(std, 4),
        "median":    round(median, 4),
        "min":       round(minimum, 4),
        "max":       round(maximum, 4),
        "skewness":  round(skewness, 4),
        "kurtosis":  round(kurtosis, 4),
        "q1":        round(q1, 4),
        "q3":        round(q3, 4),
        "histogram": histogram,
    }


# ---------------------------------------------------------------------------
# _bimodality_coefficient
# ---------------------------------------------------------------------------

def _bimodality_coefficient(skewness: float, kurtosis_excess: float, n: int) -> float:
    """
    Bimodality Coefficient (BC).
    BC > 0.555 is used as a lightweight heuristic indicator for multimodal
    distributions and avoids unstable native dependencies on Windows/Python 3.12.

    Formula:
      BC = (skewness^2 + 1) / (kurtosis + 3*(n-1)^2/((n-2)*(n-3)))
    For n <= 3 the formula is undefined; return 0.0.
    """
    if n <= 3:
        return 0.0
    correction = 3.0 * ((n - 1) ** 2) / ((n - 2) * (n - 3))
    denominator = kurtosis_excess + correction
    if denominator == 0:
        return 0.0
    return (skewness ** 2 + 1.0) / denominator


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------

def detect_anomalies(
    scores:       list[float],
    max_possible: float,
    raw_stats:    dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Detect PRD-specified anomalies in the score distribution.

    Returns a list of anomaly dicts matching AnomalyItem schema:
      [{type, severity, description, threshold, observed_value}]
    """
    anomalies: list[dict[str, Any]] = []
    n = len(scores)
    if n == 0:
        return anomalies

    skewness = raw_stats.get("skewness", 0.0)
    kurtosis = raw_stats.get("kurtosis", 0.0)

    # --- Zero inflation ---
    zero_count = sum(1 for s in scores if s == 0.0)
    zero_rate  = zero_count / n
    if zero_rate > _ZERO_INFLATION_THRESH:
        anomalies.append({
            "type":           ZERO_INFLATION,
            "severity":       SEVERITY_CRITICAL if zero_rate > 0.30 else SEVERITY_WARNING,
            "description":    (
                f"{zero_count}/{n} students ({zero_rate:.1%}) scored zero. "
                "This may indicate a missed exam or a marking issue."
            ),
            "threshold":      _ZERO_INFLATION_THRESH,
            "observed_value": round(zero_rate, 4),
        })

    # --- Ceiling effect ---
    ceil_count = sum(1 for s in scores if s >= max_possible)
    ceil_rate  = ceil_count / n
    if ceil_rate > _CEILING_EFFECT_THRESH:
        anomalies.append({
            "type":           CEILING_EFFECT,
            "severity":       SEVERITY_WARNING,
            "description":    (
                f"{ceil_count}/{n} students ({ceil_rate:.1%}) achieved full marks. "
                "The paper may have been too easy."
            ),
            "threshold":      _CEILING_EFFECT_THRESH,
            "observed_value": round(ceil_rate, 4),
        })

    # --- Bimodality (BC heuristic) ---
    bc = _bimodality_coefficient(skewness, kurtosis, n)
    if bc > _BC_BIMODAL_THRESH:
        anomalies.append({
            "type":           BIMODAL,
            "severity":       SEVERITY_WARNING,
            "description":    (
                f"Bimodality Coefficient BC={bc:.3f} exceeds threshold {_BC_BIMODAL_THRESH}. "
                "The distribution may have two distinct score clusters."
            ),
            "threshold":      _BC_BIMODAL_THRESH,
            "observed_value": round(bc, 4),
        })

    # --- Excessive skew ---
    abs_skew = abs(skewness)
    if abs_skew > _SKEW_THRESH:
        direction = "right (positive)" if skewness > 0 else "left (negative)"
        anomalies.append({
            "type":           EXCESSIVE_SKEW,
            "severity":       SEVERITY_WARNING,
            "description":    (
                f"Skewness={skewness:.3f} is {direction}-skewed (threshold ±{_SKEW_THRESH}). "
                "Grade distribution may not reflect a normal performance curve."
            ),
            "threshold":      _SKEW_THRESH,
            "observed_value": round(abs_skew, 4),
        })

    return anomalies


# ---------------------------------------------------------------------------
# cross_evaluator_stats
# ---------------------------------------------------------------------------

def cross_evaluator_stats(evaluator_rows: list[dict]) -> list[dict[str, Any]]:
    """
    Compute z-score based outlier flags for each evaluator.

    evaluator_rows: [{evaluator_id, mean, std, count}]  (from M09LedgerRepository)
    Returns: [{evaluator_id, mean, std, count, z_score, is_outlier}]
    """
    if not evaluator_rows:
        return []

    means = [float(r["mean"] or 0) for r in evaluator_rows]
    if len(means) < 2:
        return [
            {
                "evaluator_id": str(r["evaluator_id"]),
                "mean":         round(float(r["mean"] or 0), 4),
                "std":          round(float(r["std"] or 0), 4),
                "count":        int(r["count"]),
                "z_score":      0.0,
                "is_outlier":   False,
            }
            for r in evaluator_rows
        ]

    import numpy as np
    from scipy.stats import zscore as sp_zscore

    mean_arr    = np.array(means, dtype=float)
    z_scores    = sp_zscore(mean_arr, ddof=1) if len(mean_arr) > 1 else np.zeros_like(mean_arr)

    result = []
    for i, row in enumerate(evaluator_rows):
        z = float(z_scores[i]) if not math.isnan(float(z_scores[i])) else 0.0
        result.append({
            "evaluator_id": str(row["evaluator_id"]),
            "mean":         round(float(row["mean"] or 0), 4),
            "std":          round(float(row["std"] or 0), 4),
            "count":        int(row["count"]),
            "z_score":      round(z, 4),
            "is_outlier":   abs(z) > _EVALUATOR_ZSCORE_THRESH,
        })
    return result


# ---------------------------------------------------------------------------
# suggest_normalisation
# ---------------------------------------------------------------------------

def suggest_normalisation(
    scores:    list[float],
    max_marks: float,
    raw_stats: dict[str, Any],
    anomalies: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Choose the best normalisation method + params based on observed distribution.

    Selection logic:
    - If zero_inflation OR bimodal → NONE (normalisation won't help structural issues)
    - If ceiling_effect → BOUNDARY_SHIFT down by one grade step
    - If excessive_skew with mean < 0.5 * max_marks → LINEAR_SCALE to bring mean to 60%
    - Otherwise → PERCENTILE_MAP to target mean = 0.60 * max_marks
    - If no anomalies → NONE (distribution looks healthy)
    """
    anomaly_types = {a["type"] for a in anomalies}
    mean    = raw_stats.get("mean", 0.0)
    std     = raw_stats.get("std", 0.0)
    target  = round(0.60 * max_marks, 2)

    if not anomalies:
        return {
            "method":    NormalisationMethod_NONE,
            "params":    {},
            "reasoning": "No anomalies detected. Raw scores appear well-distributed.",
            "projected_stats": None,
        }

    if ZERO_INFLATION in anomaly_types or BIMODAL in anomaly_types:
        return {
            "method":    NormalisationMethod_NONE,
            "params":    {},
            "reasoning": (
                "Zero inflation or bimodal distribution detected. "
                "Statistical normalisation cannot resolve underlying data quality issues. "
                "Board should investigate marking consistency."
            ),
            "projected_stats": None,
        }

    if CEILING_EFFECT in anomaly_types:
        return {
            "method":    "BOUNDARY_SHIFT",
            "params":    {"shift_amount": 5.0, "direction": "UP"},
            "reasoning": (
                "Ceiling effect detected. Suggests shifting grade boundaries upward "
                "by 5 marks to better differentiate high performers."
            ),
            "projected_stats": None,
        }

    if EXCESSIVE_SKEW in anomaly_types and mean < 0.5 * max_marks:
        scale = min(target / mean, 1.50) if mean > 0 else 1.0
        return {
            "method":    "LINEAR_SCALE",
            "params":    {"scale_factor": round(scale, 4)},
            "reasoning": (
                f"Positive skew with low mean ({mean:.1f}/{max_marks:.0f}). "
                f"Linear scaling by {scale:.2f}x would bring mean closer to {target:.0f}."
            ),
            "projected_stats": None,
        }

    return {
        "method":    "PERCENTILE_MAP",
        "params":    {"target_mean": target, "target_max": max_marks},
        "reasoning": (
            f"Excessive skew detected. Percentile mapping to target mean "
            f"{target:.1f}/{max_marks:.0f} will produce a more balanced distribution."
        ),
        "projected_stats": None,
    }


# Avoid circular import — define string constants for methods used in suggest_normalisation
NormalisationMethod_NONE = "NONE"
