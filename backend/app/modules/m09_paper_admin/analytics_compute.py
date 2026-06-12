"""
M09.8 Examination Analytics — pure computation core.

This module is the *reusable analytics foundation*.  It contains ZERO database
or framework dependencies: every function takes already-loaded, normalised rows
(plain dataclasses) and returns plain dataclasses / dicts.  This keeps the maths
fully unit-testable without a DB, and lets future analytics modules (e.g. M10
bell-curve, programme-level dashboards) plug into the same primitives.

Design contract
---------------
  * Inputs are normalised row dataclasses (ScoreRow / EvalRow / RevalRow /
    ModRow) produced by analytics_repository from the canonical exam tables.
  * All percentages are 0–100 floats, rounded to 1–2 dp on output only.
  * Empty inputs NEVER raise — they return zero-filled / None-filled results so
    dashboards render an "empty state" rather than an error.
  * No function mutates its inputs.

"AI advises, humans decide": analytics here are descriptive only.  Nothing in
this module changes a grade, applies a penalty, or finalises a result.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field


# ===========================================================================
# Normalised input rows
# ===========================================================================

@dataclass(frozen=True)
class ScoreRow:
    """One finalised script score (from exam_score_ledger, identity already revealed)."""
    script_id:            str
    exam_paper_id:        str
    student_user_id:      str | None
    total_marks:          float
    max_marks:            float
    has_board_adjustment: bool = False
    admission_year:       int | None = None     # "batch" dimension (SIS)

    @property
    def pct(self) -> float:
        if self.max_marks <= 0:
            return 0.0
        return self.total_marks / self.max_marks * 100.0


@dataclass(frozen=True)
class EvalRow:
    """One evaluator's awarded total for one script (faculty analytics)."""
    script_id:        str
    evaluator_id:     str
    awarded_total:    float
    max_marks:        float
    turnaround_hours: float | None = None       # submitted_at - created_at


@dataclass(frozen=True)
class RevalRow:
    """One revaluation request outcome (revaluation analytics)."""
    request_id:     str
    status:         str
    original_total: float
    awarded_total:  float | None                # max(original, revaluation); None until decided


@dataclass(frozen=True)
class ModRow:
    """One moderation review (moderation analytics)."""
    review_id:       str
    status:          str
    primary_total:   float
    secondary_total: float
    variance_pct:    float
    moderated_total: float | None = None        # MODERATION-round total, if completed


# ===========================================================================
# Grade bands  (percentage-of-max → letter grade)
# ===========================================================================

# Ordered high → low.  grade_for_pct returns the first band whose floor is met.
GRADE_BANDS: list[tuple[str, float]] = [
    ("A+", 90.0),
    ("A",  80.0),
    ("B+", 70.0),
    ("B",  60.0),
    ("C",  50.0),
    ("D",  40.0),
    ("F",   0.0),
]
GRADE_ORDER: list[str] = [g for g, _ in GRADE_BANDS]

DEFAULT_PASS_PCT = 40.0


def grade_for_pct(pct: float) -> str:
    """Map a 0–100 percentage to a letter grade using GRADE_BANDS."""
    for grade, floor in GRADE_BANDS:
        if pct >= floor:
            return grade
    return "F"


# ===========================================================================
# Result containers
# ===========================================================================

@dataclass
class StatSummary:
    """Central-tendency summary for a set of scores (percentages)."""
    count:    int = 0
    average:  float | None = None
    median:   float | None = None
    highest:  float | None = None
    lowest:   float | None = None
    std_dev:  float | None = None


@dataclass
class OverviewStats:
    total_students:   int = 0
    appeared:         int = 0
    absent:           int = 0
    pass_count:       int = 0
    fail_count:       int = 0
    pass_pct:         float | None = None
    average_pct:      float | None = None
    highest_pct:      float | None = None
    lowest_pct:       float | None = None
    pass_threshold_pct: float = DEFAULT_PASS_PCT


@dataclass
class SubjectStat:
    exam_paper_id: str
    count:         int
    average:       float | None
    median:        float | None
    highest:       float | None
    lowest:        float | None
    pass_count:    int
    fail_count:    int
    pass_pct:      float | None
    fail_pct:      float | None


@dataclass
class FacultyStat:
    evaluator_id:        str
    scripts_evaluated:   int
    average_awarded_pct: float | None
    average_awarded_marks: float | None
    avg_turnaround_hours: float | None


@dataclass
class BatchStat:
    admission_year:  int | None
    count:           int
    average:         float | None
    pass_pct:        float | None
    topper_pct:      float | None
    topper_user_id:  str | None


@dataclass
class GradeBucket:
    grade: str
    count: int
    pct_of_total: float


@dataclass
class RevaluationStats:
    total_requests:   int = 0
    decided:          int = 0
    marks_increased:  int = 0
    marks_unchanged:  int = 0
    average_increase: float | None = None
    max_increase:     float | None = None


@dataclass
class ModerationStats:
    scripts_moderated:    int = 0
    completed:            int = 0
    pending:              int = 0
    average_variance_pct: float | None = None
    average_delta:        float | None = None   # avg(moderated - primary), signed


# ===========================================================================
# Low-level helpers
# ===========================================================================

def _summarise(pcts: list[float]) -> StatSummary:
    """Central-tendency summary over a list of percentages."""
    if not pcts:
        return StatSummary()
    return StatSummary(
        count=len(pcts),
        average=round(statistics.mean(pcts), 2),
        median=round(statistics.median(pcts), 2),
        highest=round(max(pcts), 2),
        lowest=round(min(pcts), 2),
        std_dev=round(statistics.pstdev(pcts), 2) if len(pcts) > 1 else 0.0,
    )


def _round1(v: float | None) -> float | None:
    return round(v, 1) if v is not None else None


# ===========================================================================
# Category computations
# ===========================================================================

def compute_overview(
    rows: list[ScoreRow],
    *,
    total_students: int | None = None,
    pass_pct: float = DEFAULT_PASS_PCT,
) -> OverviewStats:
    """
    Examination overview.

    `rows` are the finalised scores (= appeared students).  `total_students` is
    the roster size (scripts uploaded / enrolled); absentees = total - appeared.
    When `total_students` is None we assume appeared == total (no absentee data).
    """
    appeared = len(rows)
    total = total_students if total_students is not None else appeared
    total = max(total, appeared)  # never let absent go negative
    absent = total - appeared

    pcts = [r.pct for r in rows]
    pass_count = sum(1 for p in pcts if p >= pass_pct)
    fail_count = appeared - pass_count

    return OverviewStats(
        total_students=total,
        appeared=appeared,
        absent=absent,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_pct=round(pass_count / appeared * 100, 1) if appeared else None,
        average_pct=round(statistics.mean(pcts), 1) if pcts else None,
        highest_pct=round(max(pcts), 1) if pcts else None,
        lowest_pct=round(min(pcts), 1) if pcts else None,
        pass_threshold_pct=pass_pct,
    )


def compute_subject_stats(
    rows: list[ScoreRow],
    *,
    pass_pct: float = DEFAULT_PASS_PCT,
) -> list[SubjectStat]:
    """Per-exam-paper (subject) statistics, sorted by average ascending (hardest first)."""
    grouped: dict[str, list[ScoreRow]] = {}
    for r in rows:
        grouped.setdefault(r.exam_paper_id, []).append(r)

    out: list[SubjectStat] = []
    for paper_id, group in grouped.items():
        pcts = [r.pct for r in group]
        s = _summarise(pcts)
        pass_count = sum(1 for p in pcts if p >= pass_pct)
        fail_count = len(pcts) - pass_count
        out.append(SubjectStat(
            exam_paper_id=paper_id,
            count=len(pcts),
            average=s.average,
            median=s.median,
            highest=s.highest,
            lowest=s.lowest,
            pass_count=pass_count,
            fail_count=fail_count,
            pass_pct=round(pass_count / len(pcts) * 100, 1) if pcts else None,
            fail_pct=round(fail_count / len(pcts) * 100, 1) if pcts else None,
        ))
    # Hardest subjects (lowest average) first; None averages sink to the end.
    out.sort(key=lambda x: (x.average is None, x.average if x.average is not None else 0))
    return out


def compute_faculty_stats(rows: list[EvalRow]) -> list[FacultyStat]:
    """Per-evaluator workload and marking-pattern statistics, busiest first."""
    grouped: dict[str, list[EvalRow]] = {}
    for r in rows:
        grouped.setdefault(r.evaluator_id, []).append(r)

    out: list[FacultyStat] = []
    for evaluator_id, group in grouped.items():
        pcts = [
            (r.awarded_total / r.max_marks * 100.0)
            for r in group if r.max_marks > 0
        ]
        marks = [r.awarded_total for r in group]
        turnarounds = [r.turnaround_hours for r in group if r.turnaround_hours is not None]
        out.append(FacultyStat(
            evaluator_id=evaluator_id,
            scripts_evaluated=len(group),
            average_awarded_pct=round(statistics.mean(pcts), 1) if pcts else None,
            average_awarded_marks=round(statistics.mean(marks), 2) if marks else None,
            avg_turnaround_hours=round(statistics.mean(turnarounds), 1) if turnarounds else None,
        ))
    out.sort(key=lambda x: x.scripts_evaluated, reverse=True)
    return out


def compute_batch_stats(
    rows: list[ScoreRow],
    *,
    pass_pct: float = DEFAULT_PASS_PCT,
) -> list[BatchStat]:
    """Per-admission-year (batch) statistics, newest batch first."""
    grouped: dict[int | None, list[ScoreRow]] = {}
    for r in rows:
        grouped.setdefault(r.admission_year, []).append(r)

    out: list[BatchStat] = []
    for year, group in grouped.items():
        pcts = [r.pct for r in group]
        pass_count = sum(1 for p in pcts if p >= pass_pct)
        topper = max(group, key=lambda r: r.pct) if group else None
        out.append(BatchStat(
            admission_year=year,
            count=len(group),
            average=round(statistics.mean(pcts), 1) if pcts else None,
            pass_pct=round(pass_count / len(pcts) * 100, 1) if pcts else None,
            topper_pct=round(topper.pct, 1) if topper else None,
            topper_user_id=topper.student_user_id if topper else None,
        ))
    # Newest batch first; unknown (None) batch sinks to the end.
    out.sort(key=lambda x: (x.admission_year is None, -(x.admission_year or 0)))
    return out


def compute_grade_distribution(rows: list[ScoreRow]) -> list[GradeBucket]:
    """Histogram-ready grade buckets covering every band in GRADE_ORDER (zero-filled)."""
    counts: dict[str, int] = {g: 0 for g in GRADE_ORDER}
    for r in rows:
        counts[grade_for_pct(r.pct)] += 1
    total = len(rows)
    return [
        GradeBucket(
            grade=g,
            count=counts[g],
            pct_of_total=round(counts[g] / total * 100, 1) if total else 0.0,
        )
        for g in GRADE_ORDER
    ]


def compute_revaluation_stats(rows: list[RevalRow]) -> RevaluationStats:
    """Revaluation outcome analytics."""
    total = len(rows)
    decided_rows = [r for r in rows if r.awarded_total is not None]
    increases = [
        r.awarded_total - r.original_total
        for r in decided_rows
        if r.awarded_total is not None and r.awarded_total > r.original_total
    ]
    increased = len(increases)
    unchanged = sum(
        1 for r in decided_rows
        if r.awarded_total is not None and r.awarded_total <= r.original_total
    )
    return RevaluationStats(
        total_requests=total,
        decided=len(decided_rows),
        marks_increased=increased,
        marks_unchanged=unchanged,
        average_increase=round(statistics.mean(increases), 2) if increases else 0.0 if decided_rows else None,
        max_increase=round(max(increases), 2) if increases else 0.0 if decided_rows else None,
    )


def compute_moderation_stats(rows: list[ModRow]) -> ModerationStats:
    """Moderation analytics: counts, average flagged variance, average correction delta."""
    total = len(rows)
    completed = [r for r in rows if r.moderated_total is not None]
    pending = total - len(completed)
    variances = [r.variance_pct for r in rows]
    # Delta = how much the moderator moved the score off the primary evaluator.
    deltas = [
        r.moderated_total - r.primary_total
        for r in completed if r.moderated_total is not None
    ]
    return ModerationStats(
        scripts_moderated=total,
        completed=len(completed),
        pending=pending,
        average_variance_pct=round(statistics.mean(variances), 2) if variances else None,
        average_delta=round(statistics.mean(deltas), 2) if deltas else None,
    )
