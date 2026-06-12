"""
M09.9 Compliance & Audit — pure core (no DB, no I/O).

This module is the DB-free heart of the compliance subsystem, mirroring the
``analytics_compute`` convention: all classification, timeline assembly, report
shaping and CSV serialisation live here as pure functions so they can be unit
tested in isolation.

Two responsibilities:

1. The **examination event taxonomy** — a curated mapping from the global
   ``AuditEventType`` values to a compliance *category* and a human-readable
   *label*.  The compliance layer reads the canonical ``public.audit_logs``
   stream but only surfaces the events that matter for examination governance.

2. **Pure transformations** — building chronological timelines, deriving the
   per-question mark-change lineage from evaluation snapshots, and rendering any
   list of dict rows to RFC-4180 CSV for compliance exports.

Nothing here mutates examination data.  ("AI advises, humans decide.")
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable


# ===========================================================================
# Compliance categories
# ===========================================================================

class Category:
    MARK_CHANGE    = "MARK_CHANGE"
    EVALUATION     = "EVALUATION"
    MODERATION     = "MODERATION"
    REVALUATION    = "REVALUATION"
    BOARD_APPROVAL = "BOARD_APPROVAL"
    PUBLICATION    = "PUBLICATION"
    ASSIGNMENT     = "ASSIGNMENT"
    SCANNING       = "SCANNING"


# Curated taxonomy: AuditEventType.value -> (category, human label).
# Only examination-governance events appear here; everything else in the global
# audit stream is intentionally excluded from compliance views.
EXAM_EVENT_CATALOG: dict[str, tuple[str, str]] = {
    # --- scanning / ingest ---
    "SCRIPT_QUALITY_CHECK_COMPLETED": (Category.SCANNING, "Scan quality check completed"),
    "SCRIPT_QUALITY_OVERRIDDEN":      (Category.SCANNING, "Scan quality overridden by admin"),
    "SCRIPT_OCR_COMPLETED":           (Category.SCANNING, "OCR completed"),

    # --- evaluation / mark changes ---
    "SCRIPT_EVALUATOR_ASSIGNED": (Category.EVALUATION,  "Evaluator assigned to script"),
    "SCRIPT_SCORING_COMPLETED":  (Category.EVALUATION,  "AI scoring completed"),
    "SCRIPT_MARKS_UPDATED":      (Category.MARK_CHANGE, "Marks changed"),
    "SCRIPT_MARKS_SUBMITTED":    (Category.MARK_CHANGE, "Marks submitted (Gate 1)"),
    "SCRIPT_BOARD_FINALISED":    (Category.MARK_CHANGE, "Marks finalised by Board (Gate 2)"),
    "EXAM_SCORE_RECORDED":       (Category.MARK_CHANGE, "Score recorded to ledger"),

    # --- moderation ---
    "SCRIPT_MODERATION_FLAGGED":   (Category.MODERATION, "Script flagged for moderation"),
    "SCRIPT_MODERATION_SUBMITTED": (Category.MODERATION, "Moderation marks submitted"),

    # --- board approval ---
    "BOARD_SESSION_CONVENED": (Category.BOARD_APPROVAL, "Board session convened"),
    "BOARD_SESSION_APPROVED": (Category.BOARD_APPROVAL, "Board approved results"),
    "BOARD_SESSION_REJECTED": (Category.BOARD_APPROVAL, "Board rejected results"),

    # --- publication ---
    "RESULTS_DECLARED": (Category.PUBLICATION, "Results declared to students"),

    # --- revaluation ---
    "REVALUATION_REQUESTED":       (Category.REVALUATION, "Revaluation requested"),
    "REVALUATION_ACCEPTED":        (Category.REVALUATION, "Revaluation accepted"),
    "REVALUATION_REJECTED":        (Category.REVALUATION, "Revaluation rejected at intake"),
    "REVALUATION_MARKS_SUBMITTED": (Category.REVALUATION, "Revaluation marks submitted"),
    "REVALUATION_BOARD_RATIFIED":  (Category.REVALUATION, "Revaluation ratified by Board"),
    "REVALUATION_BOARD_REJECTED":  (Category.REVALUATION, "Revaluation rejected by Board"),

    # --- assignment engine ---
    "ASSIGNMENT_CREATED":       (Category.ASSIGNMENT, "Work assigned to evaluator"),
    "ASSIGNMENT_REASSIGNED":    (Category.ASSIGNMENT, "Work reassigned"),
    "ASSIGNMENT_SUBMITTED":     (Category.ASSIGNMENT, "Assignment submitted"),
    "ASSIGNMENT_COMPLETED":     (Category.ASSIGNMENT, "Assignment completed"),
    "ASSIGNMENT_CANCELLED":     (Category.ASSIGNMENT, "Assignment cancelled"),
    "AUTO_ASSIGNMENT_EXECUTED": (Category.ASSIGNMENT, "Auto-assignment batch executed"),
}

# Frozen set of event-type strings the compliance layer surfaces — used by the
# repository to filter ``public.audit_logs`` down to examination governance.
EXAM_EVENT_TYPES: frozenset[str] = frozenset(EXAM_EVENT_CATALOG.keys())

ALL_CATEGORIES: tuple[str, ...] = (
    Category.MARK_CHANGE, Category.EVALUATION, Category.MODERATION,
    Category.REVALUATION, Category.BOARD_APPROVAL, Category.PUBLICATION,
    Category.ASSIGNMENT, Category.SCANNING,
)


def is_exam_event(event_type: str) -> bool:
    """True if the event type participates in examination compliance."""
    return event_type in EXAM_EVENT_CATALOG


def category_for(event_type: str) -> str | None:
    entry = EXAM_EVENT_CATALOG.get(event_type)
    return entry[0] if entry else None


def label_for(event_type: str) -> str:
    """Human-readable label; falls back to a title-cased event type."""
    entry = EXAM_EVENT_CATALOG.get(event_type)
    if entry:
        return entry[1]
    return event_type.replace("_", " ").title()


def event_types_for_categories(categories: Iterable[str] | None) -> list[str] | None:
    """Translate a category filter into the concrete event-type list to query.

    Returns None when no category filter is supplied (meaning: all exam events).
    """
    if not categories:
        return None
    wanted = {c.upper() for c in categories}
    return [et for et, (cat, _) in EXAM_EVENT_CATALOG.items() if cat in wanted]


# ===========================================================================
# Timeline assembly
# ===========================================================================

@dataclass
class TimelineEntry:
    id: str
    event_type: str
    category: str
    label: str
    actor_user_id: str | None
    actor_role: str | None
    actor_name: str | None
    target_entity: str | None
    target_id: str | None
    occurred_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


def build_timeline(
    rows: list[dict[str, Any]],
    *,
    names: dict[str, str] | None = None,
    descending: bool = True,
) -> list[TimelineEntry]:
    """Turn raw audit rows into a sorted, enriched compliance timeline.

    Each ``row`` is a mapping with at least: id, event_type, actor_user_id,
    actor_role, target_entity, target_id, created_at, metadata.
    Non-examination events are dropped.  ``names`` maps user_id -> display name.
    """
    names = names or {}
    entries: list[TimelineEntry] = []
    for r in rows:
        et = r["event_type"]
        if not is_exam_event(et):
            continue
        actor = str(r["actor_user_id"]) if r.get("actor_user_id") else None
        entries.append(TimelineEntry(
            id=str(r["id"]),
            event_type=et,
            category=category_for(et) or "OTHER",
            label=label_for(et),
            actor_user_id=actor,
            actor_role=r.get("actor_role"),
            actor_name=names.get(actor) if actor else None,
            target_entity=r.get("target_entity"),
            target_id=str(r["target_id"]) if r.get("target_id") else None,
            occurred_at=r["created_at"],
            metadata=r.get("metadata") or {},
        ))
    entries.sort(key=lambda e: e.occurred_at, reverse=descending)
    return entries


def summarise_categories(entries: list[TimelineEntry]) -> dict[str, int]:
    """Count entries per category (zero-filled across all categories)."""
    counts = {c: 0 for c in ALL_CATEGORIES}
    for e in entries:
        if e.category in counts:
            counts[e.category] += 1
    return counts


# ===========================================================================
# Mark-change lineage (derived from evaluation snapshots)
# ===========================================================================

@dataclass
class MarkLineageStep:
    stage: str            # AI_SUGGESTED / EVALUATOR / MODERATION / BOARD_ADJUSTED / FINAL / REVALUATION
    marks: float | None
    max_marks: float | None
    note: str | None = None


@dataclass
class QuestionMarkHistory:
    question_id: str
    question_type: str | None
    max_marks: float | None
    steps: list[MarkLineageStep]


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def derive_question_lineage(eval_rows: list[dict[str, Any]]) -> list[QuestionMarkHistory]:
    """Reconstruct each question's value lineage from script_evaluations rows.

    The evaluation table already preserves the full lineage per question:
        ai_suggested_marks → evaluator_marks → board_adjusted_marks → final_marks
    across PRIMARY / SECONDARY / MODERATION rounds.  This turns those columns into
    an ordered, human-readable change history without any extra storage.
    """
    by_q: dict[str, QuestionMarkHistory] = {}
    # Stable round ordering so the lineage reads chronologically.
    round_order = {"PRIMARY": 0, "SECONDARY": 1, "MODERATION": 2}
    for r in sorted(eval_rows, key=lambda x: round_order.get(x.get("evaluation_round", ""), 9)):
        qid = str(r["question_id"])
        rnd = r.get("evaluation_round") or "PRIMARY"
        steps: list[MarkLineageStep] = []
        if r.get("ai_suggested_marks") is not None:
            steps.append(MarkLineageStep("AI_SUGGESTED", _f(r["ai_suggested_marks"]), _f(r.get("max_marks")),
                                         r.get("ai_justification")))
        if r.get("evaluator_marks") is not None:
            stage = "MODERATION" if rnd == "MODERATION" else "EVALUATOR"
            steps.append(MarkLineageStep(stage, _f(r["evaluator_marks"]), _f(r.get("max_marks")),
                                         r.get("evaluator_note")))
        if r.get("board_adjusted_marks") is not None:
            steps.append(MarkLineageStep("BOARD_ADJUSTED", _f(r["board_adjusted_marks"]), _f(r.get("max_marks")),
                                         r.get("board_adjustment_note")))
        if r.get("final_marks") is not None:
            steps.append(MarkLineageStep("FINAL", _f(r["final_marks"]), _f(r.get("max_marks"))))

        existing = by_q.get(qid)
        if existing is None:
            by_q[qid] = QuestionMarkHistory(
                question_id=qid,
                question_type=r.get("question_type"),
                max_marks=_f(r.get("max_marks")),
                steps=steps,
            )
        else:
            existing.steps.extend(steps)
    return list(by_q.values())


def compute_delta(previous: float | None, new: float | None) -> float | None:
    if previous is None or new is None:
        return None
    return round(new - previous, 2)


# ===========================================================================
# CSV serialisation (RFC 4180)
# ===========================================================================

def to_csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Render dict rows to CSV text with the given ordered columns.

    Missing keys render as empty cells; values are stringified.  A header row is
    always emitted (even for empty ``rows``) so exports are self-describing.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: _cell(r.get(c)) for c in columns})
    return buf.getvalue()


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
