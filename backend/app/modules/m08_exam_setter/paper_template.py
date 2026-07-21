"""
M08 Exam Setter — Paper Template: the source of truth for a paper's structure.

    PaperTemplate ──compile_specs()──▶ QuestionSpec[] ──▶ AI writes content
                                            │                    │
                                            └──────▶ Editor ◀────┘
                                                        │
                                                        ▼
                                                       PDF

The model is what a faculty member already has in their head:

    Paper
      └── Section              a logical grouping. HAS NO UNIT.
            ├── name           free text — "A", "Part A", "Module 1", anything
            ├── instruction    printed verbatim
            ├── answer_rule    ALL | ANY_K(k)   — counts printed questions
            └── QuestionDefinition[]
                  ├── count       how many questions to write
                  ├── marks       each
                  ├── units       which units they come from (a pool)
                  ├── unit_mode   DISTRIBUTE (spread over the pool)
                  │               INTEGRATE  (every question draws on the whole pool)
                  ├── type        AUTO | MCQ | SHORT | LONG | PROBLEM | CASE_STUDY | PROGRAMMING
                  ├── bloom       null = inherit the paper's global distribution
                  ├── difficulty  null = inherit
                  ├── co          AUTO | specific CO ids
                  ├── or_choice   print two alternatives, answer one
                  └── parts[]     optional sub-parts a) b) c)

Nothing here names a university, and there are no template "types". Every
pattern is expressed by choosing sections, rules and definitions:

    "answer any FIVE of EIGHT"  → one section, ANY_K(5), one definition count=8
    "10 x 2 marks, all units"   → one section, ALL, one definition count=10
    "Q1 OR Q2, one per module"  → one section per module, ANY_K(1), two definitions
    "Q1 a) b) c)"               → a definition with parts

Faculty never write per-unit rows and never place individual questions. They say
"8 questions, 6 marks, these units" and THE COMPILER decides the distribution —
deterministically, so the paper is reproducible and the AI is never asked to make
a structural decision. The AI only writes the text of a question it is fully told
the shape of.

Unit resolution
---------------
A definition's `units` is a pool. Empty/None means "all the units the paper
covers". Units always come from the paper's own units_included, which come from
the course's approved syllabus — so a template is course-agnostic and adapts when
the syllabus changes. Nothing is ever fabricated.

Versioning
----------
The document carries `version`. v1 (P1.16/17) and v2 (P1.18) are upgraded in
memory by normalise_definition(); stored documents are never rewritten, so a
sealed paper keeps printing exactly what it printed the day it was sealed. That
same property is what lets a future shared-template library hand out definitions
without ever mutating a paper made from one.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("vidya.m08.paper_template")

TEMPLATE_VERSION = 3

# Answer rules — the whole choice system.
ALL   = "ALL"
ANY_K = "ANY_K"

# Unit pool semantics.
DISTRIBUTE = "DISTRIBUTE"   # spread the questions across the pool
INTEGRATE  = "INTEGRATE"    # every question draws on the whole pool

# What a definition asks the AI to write. AUTO lets marks decide.
QUESTION_TYPES = (
    "AUTO", "MCQ", "SHORT", "LONG", "PROBLEM", "CASE_STUDY", "PROGRAMMING",
)

DIFFICULTIES = ("EASY", "MEDIUM", "HARD")

# The persisted question_type vocabulary (exam_questions.question_type). The
# builder's richer vocabulary maps onto it; the column is a plain VARCHAR, so the
# two new kinds need no migration.
_TYPE_TO_STORED = {
    "MCQ":         "MCQ",
    "SHORT":       "SHORT_ANSWER",
    "LONG":        "LONG_ANSWER",
    "PROBLEM":     "PROBLEM_SOLVING",
    "CASE_STUDY":  "CASE_STUDY",
    "PROGRAMMING": "PROGRAMMING",
}


def _fmt(v: float) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


def _sid(obj: dict, prefix: str, index: int) -> str:
    """A stable id, falling back to position for documents written before ids."""
    return str(obj.get("id") or f"{prefix}{index}")


def stored_question_type(t: str | None, marks: float) -> str:
    """Map a definition's type onto the stored vocabulary. AUTO infers from marks —
    the same rule the generator has always used."""
    t = (t or "AUTO").upper()
    if t in _TYPE_TO_STORED:
        return _TYPE_TO_STORED[t]
    return "SHORT_ANSWER" if marks <= 2 else "LONG_ANSWER"


# ---------------------------------------------------------------------------
# Document normalisation (v1 / v2 -> v3)
# ---------------------------------------------------------------------------

def _blank_doc() -> dict:
    return {"version": TEMPLATE_VERSION, "sections": []}


def _new_definition(**kw: Any) -> dict:
    d = {
        "id":         kw.get("id"),
        "count":      int(kw.get("count") or 1),
        "marks":      float(kw.get("marks") or 0),
        "units":      list(kw.get("units") or []),
        "unit_mode":  kw.get("unit_mode") or DISTRIBUTE,
        "type":       kw.get("type") or "AUTO",
        "bloom":      kw.get("bloom"),
        "difficulty": kw.get("difficulty"),
        "co_mode":    kw.get("co_mode") or "AUTO",
        "co_ids":     list(kw.get("co_ids") or []),
        "or_choice":  bool(kw.get("or_choice")),
        "parts":      list(kw.get("parts") or []),
    }
    return d


def normalise_definition(tdef: Any) -> dict:
    """Return a v3 document, upgrading older shapes in memory.

    v1 put one unit on each block; v2 gave every slot its own unit; both had
    template "types" and a separate block kind per pattern. v3 has one shape:
    sections of question definitions. The upgrades below reproduce exactly what an
    older paper already printed — each old block becomes its own section, so
    headers, order and totals are unchanged.
    """
    if not isinstance(tdef, dict):
        return _blank_doc()

    version = int(tdef.get("version") or 1)
    if version >= TEMPLATE_VERSION:
        return {
            "version":  version,
            "sections": list(tdef.get("sections") or []),
        }

    sections: list[dict] = []
    blocks = list(tdef.get("blocks") or [])
    groups = {str(g.get("id")): g for g in (tdef.get("groups") or []) if g.get("id")}

    # v2 choice groups become one section per group (a group's blocks were
    # alternatives answered k-of-n, which is exactly a section's answer rule).
    group_sections: dict[str, dict] = {}

    def _target_section(block: dict, index: int, default_name: str) -> dict:
        gid = str(block.get("group_id") or "") or None
        if gid and gid in groups:
            if gid not in group_sections:
                g = groups[gid]
                sec = {
                    "id":          f"sec_{gid}",
                    "name":        str(g.get("name") or ""),
                    "instruction": "",
                    "answer_rule": {"mode": ANY_K, "k": int(g.get("answer") or 1)},
                    "definitions": [],
                }
                group_sections[gid] = sec
                sections.append(sec)
            return group_sections[gid]
        sec = {
            "id":          f"sec_{_sid(block, 'blk', index)}",
            "name":        default_name,
            "instruction": "",
            "answer_rule": {"mode": ALL},
            "definitions": [],
        }
        sections.append(sec)
        return sec

    for i, b in enumerate(blocks):
        kind = b.get("kind")
        bid  = _sid(b, "blk", i)

        if kind == "SECTION":
            # v2 slots each carried a unit; v1 blocks carried one unit + generate.
            slots = b.get("slots")
            if slots is None:
                generate = int(b.get("generate") or 0)
                units = [b.get("unit_number")] if b.get("unit_number") is not None else []
            else:
                generate = len(slots)
                units = [s.get("unit_number") for s in slots if s.get("unit_number") is not None]
            n = max(0, generate)
            sec = {
                "id":          f"sec_{bid}",
                "name":        str(b.get("name") or ""),
                "instruction": "",
                "answer_rule": (
                    {"mode": ANY_K, "k": int(b.get("answer") or n)}
                    if int(b.get("answer") or n) < n else {"mode": ALL}
                ),
                "definitions": [_new_definition(
                    id=bid, count=n, marks=float(b.get("marks") or 0),
                    units=sorted(set(units)), unit_mode=DISTRIBUTE,
                )],
            }
            sections.append(sec)

        elif kind == "UNIT_GROUP":
            n = int(b.get("generate") or 0)
            pattern = (b.get("choice_pattern") or "COMPULSORY").upper()
            answer  = int(b.get("answer") or n)
            unit    = b.get("unit_number")
            sec = {
                "id":          f"sec_{bid}",
                "name":        f"Unit {unit}" + (f" — {b['category']}" if b.get("category") else ""),
                "instruction": "",
                "answer_rule": (
                    {"mode": ANY_K, "k": 1} if pattern == "OR_CHOICE"
                    else {"mode": ANY_K, "k": answer} if answer < n
                    else {"mode": ALL}
                ),
                "definitions": [_new_definition(
                    id=bid, count=n, marks=float(b.get("marks") or 0),
                    units=[unit] if unit is not None else [], unit_mode=DISTRIBUTE,
                )],
            }
            sections.append(sec)

        elif kind == "FULL_QUESTION":
            parts = []
            for sp in (b.get("subparts") or []):
                u = sp.get("unit_number", b.get("unit_number"))
                parts.append({
                    "marks":     float(sp.get("marks") or 0),
                    "or_choice": bool(sp.get("or_choice")),
                    "units":     [u] if u is not None else [],
                })
            sec = _target_section(b, i, str(b.get("label") or ""))
            sec["definitions"].append(_new_definition(
                id=bid, count=1, marks=0, units=[], parts=parts,
            ))

    # The oldest UNIT papers had no blocks at all — they stored the compiled
    # blueprint itself ({type: "UNIT", units: [UnitBlueprint]}). Each row becomes
    # its own section, which is what those papers already printed.
    if not sections and tdef.get("units"):
        for entry in (tdef.get("units") or []):
            un = entry.get("unit_number")
            for ri, row in enumerate(entry.get("rows") or []):
                n = int(row.get("count") or 0)
                if n <= 0:
                    continue
                pattern = (row.get("choice_pattern") or "COMPULSORY").upper()
                answer  = int(row.get("answer_count") or n)
                cat     = (row.get("category") or "").strip()
                rid     = str(row.get("template_block_id") or f"u{un}r{ri}")
                sections.append({
                    "id":          f"sec_{rid}",
                    "name":        f"Unit {un}" + (f" — {cat}" if cat else ""),
                    "instruction": "",
                    "answer_rule": (
                        {"mode": ANY_K, "k": 1} if pattern == "OR_CHOICE"
                        else {"mode": ANY_K, "k": answer} if answer < n
                        else {"mode": ALL}
                    ),
                    "definitions": [_new_definition(
                        id=rid, count=n, marks=float(row.get("marks") or 0),
                        units=[un] if un is not None else [], unit_mode=DISTRIBUTE,
                    )],
                })

    return {"version": TEMPLATE_VERSION, "sections": sections}


def has_template(paper: Any) -> bool:
    """True when a paper's structure is owned by a template document."""
    tdef = getattr(paper, "template_definition", None)
    if not tdef:
        return False
    return bool(normalise_definition(tdef).get("sections"))


# ---------------------------------------------------------------------------
# Unit resolution
# ---------------------------------------------------------------------------

class _Pool:
    """A definition's unit pool, resolved against the paper's own units.

    An empty pool means "every unit this paper covers". Distribution restarts per
    definition so each one's spread reads predictably and does not depend on how
    many questions came before it elsewhere in the paper.
    """

    def __init__(self, units: list, paper_units: list[int]) -> None:
        chosen = [int(u) for u in (units or []) if u is not None]
        allowed = [int(u) for u in (paper_units or [])]
        # Only offer units the paper actually covers; fall back to the paper's own
        # units so a template built for another course still compiles.
        pool = [u for u in chosen if not allowed or u in allowed] or allowed
        self.units = pool or [1]
        self._i = 0

    def next(self) -> int:
        u = self.units[self._i % len(self.units)]
        self._i += 1
        return u


# ---------------------------------------------------------------------------
# Spec compilation
# ---------------------------------------------------------------------------

def compile_specs(tdef: Any, units_included: list[int] | None = None) -> list[dict]:
    """Expand a template into one spec per question the paper must contain.

    A spec is everything the AI is told and everything the paper needs to
    reconstruct itself: which definition owns it, which units it covers, what it
    is worth, and the Bloom's / difficulty / CO / type asked for. Specs come back
    in printed order, which is also the order questions are numbered in.
    """
    doc = normalise_definition(tdef)
    paper_units = [int(u) for u in (units_included or [])]
    specs: list[dict] = []
    # Pairs either/or alternatives for the renderer. Numbered high so it cannot
    # collide with a value a model invented.
    or_group = 10_000

    def _add(**kw: Any) -> None:
        kw["order"] = len(specs)
        specs.append(kw)

    for si, sec in enumerate(doc["sections"]):
        sec_id   = _sid(sec, "sec", si)
        sec_name = str(sec.get("name") or "")

        for di, qd in enumerate(sec.get("definitions") or []):
            qd_id = _sid(qd, "qd", di)
            count = int(qd.get("count") or 0)
            if count <= 0:
                continue
            parts = qd.get("parts") or []
            pool  = _Pool(qd.get("units"), paper_units)
            mode  = (qd.get("unit_mode") or DISTRIBUTE).upper()

            def _units_for() -> tuple[list[int], int]:
                """(unit_numbers, primary). INTEGRATE gives the whole pool to every
                question; DISTRIBUTE hands out one unit at a time."""
                if mode == INTEGRATE:
                    return list(pool.units), pool.units[0]
                u = pool.next()
                return [u], u

            base = {
                "section_id":    sec_id,
                "section_name":  sec_name,
                "section_order": si,
                "block_id":      qd_id,      # the column is template_block_id
                "co_mode":       (qd.get("co_mode") or "AUTO").upper(),
                "co_ids":        list(qd.get("co_ids") or []),
            }

            for _n in range(count):
                if not parts:
                    marks = float(qd.get("marks") or 0)
                    if marks <= 0:
                        continue
                    units, primary = _units_for()
                    cg = None
                    if qd.get("or_choice"):
                        or_group += 1
                        cg = or_group
                    for _alt in range(2 if qd.get("or_choice") else 1):
                        _add(
                            **base, subpart_index=None,
                            unit_numbers=units, unit_number=primary, marks=marks,
                            question_type=stored_question_type(qd.get("type"), marks),
                            bloom=qd.get("bloom"), difficulty=qd.get("difficulty"),
                            category=sec_name or None, choice_group=cg,
                        )
                    continue

                # A full question: one spec per sub-part (two when the part is an
                # either/or), all sharing this definition's id.
                for pi, part in enumerate(parts):
                    pmarks = float(part.get("marks") or 0)
                    if pmarks <= 0:
                        continue
                    p_units = part.get("units")
                    if p_units:
                        ppool = _Pool(p_units, paper_units)
                        units, primary = ([int(u) for u in ppool.units], ppool.units[0]) \
                            if (part.get("unit_mode") or mode).upper() == INTEGRATE \
                            else ([ppool.next()], None)
                        if primary is None:
                            primary = units[0]
                    else:
                        units, primary = _units_for()
                    cg = None
                    if part.get("or_choice"):
                        or_group += 1
                        cg = or_group
                    for _alt in range(2 if part.get("or_choice") else 1):
                        _add(
                            **base, subpart_index=pi,
                            unit_numbers=units, unit_number=primary, marks=pmarks,
                            question_type=stored_question_type(
                                part.get("type") or qd.get("type"), pmarks
                            ),
                            bloom=part.get("bloom") or qd.get("bloom"),
                            difficulty=part.get("difficulty") or qd.get("difficulty"),
                            category=sec_name or None, choice_group=cg,
                        )

    return specs


# ---------------------------------------------------------------------------
# Totals — printed vs evaluation
# ---------------------------------------------------------------------------

def _definition_weight(qd: dict) -> float:
    """The most a student can score from ONE question of this definition.
    An either/or counts once; a full question is the sum of its parts."""
    parts = qd.get("parts") or []
    if not parts:
        return float(qd.get("marks") or 0)
    return sum(float(p.get("marks") or 0) for p in parts)


def _definition_printed(qd: dict) -> float:
    """Every mark this definition puts on the page, optional questions included."""
    count = int(qd.get("count") or 0)
    parts = qd.get("parts") or []
    if not parts:
        per = float(qd.get("marks") or 0) * (2 if qd.get("or_choice") else 1)
    else:
        per = sum(
            float(p.get("marks") or 0) * (2 if p.get("or_choice") else 1) for p in parts
        )
    return count * per


def section_weights(section: dict) -> list[float]:
    """One weight per printed question in the section — a full question counts
    once, however many parts it has. This is what an answer rule counts."""
    ws: list[float] = []
    for qd in (section.get("definitions") or []):
        w = _definition_weight(qd)
        ws.extend([w] * max(0, int(qd.get("count") or 0)))
    return ws


def section_totals(section: dict) -> tuple[float, float]:
    printed = sum(_definition_printed(qd) for qd in (section.get("definitions") or []))
    ws = section_weights(section)
    rule = section.get("answer_rule") or {"mode": ALL}
    if (rule.get("mode") or ALL).upper() == ANY_K:
        k = max(0, min(int(rule.get("k") or len(ws)), len(ws)))
        # "The most a student can score" — so the k best, when they differ.
        evaluation = sum(sorted(ws, reverse=True)[:k])
    else:
        evaluation = sum(ws)
    return printed, evaluation


def template_totals(tdef: Any) -> tuple[float, float]:
    """(printed, evaluation) for the whole paper. One rule, every pattern."""
    doc = normalise_definition(tdef)
    printed = evaluation = 0.0
    for sec in doc["sections"]:
        p, e = section_totals(sec)
        printed += p
        evaluation += e
    return printed, evaluation


def spec_count(tdef: Any, units_included: list[int] | None = None) -> int:
    return len(compile_specs(tdef, units_included))


# ---------------------------------------------------------------------------
# The AI's brief — built from specs, never from prose
# ---------------------------------------------------------------------------

def _num_word(n: int) -> str:
    words = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX",
             7: "SEVEN", 8: "EIGHT", 9: "NINE", 10: "TEN", 11: "ELEVEN",
             12: "TWELVE", 13: "THIRTEEN", 14: "FOURTEEN", 15: "FIFTEEN"}
    return words.get(int(n), str(int(n)))


def describe_for_prompt(tdef: Any, units_included: list[int] | None = None) -> str:
    """Tell the model exactly which questions to write.

    Every position is listed with its units, marks, type, Bloom's, difficulty and
    CO. The model chooses none of this — it writes the text for a shape it is
    handed, which is what keeps the paper the faculty's and not the model's.
    """
    doc = normalise_definition(tdef)
    specs = compile_specs(tdef, units_included)
    by_def: dict[str, list[dict]] = {}
    for s in specs:
        by_def.setdefault(s["block_id"], []).append(s)

    lines: list[str] = []
    for si, sec in enumerate(doc["sections"]):
        rule = sec.get("answer_rule") or {"mode": ALL}
        ws = section_weights(sec)
        if (rule.get("mode") or ALL).upper() == ANY_K:
            k = max(0, min(int(rule.get("k") or len(ws)), len(ws)))
            rule_text = f"the student answers any {k} of the {len(ws)} question(s)"
        else:
            rule_text = f"all {len(ws)} question(s) are compulsory"
        name = sec.get("name") or f"Section {si + 1}"
        instr = (sec.get("instruction") or "").strip()
        lines.append(f'\nSECTION "{name}" — {rule_text}.'
                     + (f' Printed instruction: "{instr}"' if instr else ""))

        for di, qd in enumerate(sec.get("definitions") or []):
            qd_id = _sid(qd, "qd", di)
            dspecs = by_def.get(qd_id) or []
            if not dspecs:
                continue
            qd.get("parts") or []
            mode = (qd.get("unit_mode") or DISTRIBUTE).upper()
            note = ("each question must INTEGRATE the listed units into one question"
                    if mode == INTEGRATE else
                    "each question covers the unit given for it")
            lines.append(f"  Definition {qd_id} — {note}.")
            for i, s in enumerate(dspecs, start=1):
                bits = [f"unit(s) {', '.join(str(u) for u in s['unit_numbers'])}",
                        f"{_fmt(s['marks'])} marks",
                        f"type {s['question_type']}"]
                if s.get("bloom"):
                    bits.append(f"Bloom's {s['bloom']}")
                if s.get("difficulty"):
                    bits.append(f"difficulty {s['difficulty']}")
                if s.get("co_mode") == "SPECIFIC" and s.get("co_ids"):
                    bits.append(f"CO {', '.join(str(c) for c in s['co_ids'])}")
                label = f"part {chr(97 + s['subpart_index'])})" if s.get("subpart_index") is not None else f"Q{i}"
                alt = " (one of two OR alternatives — write both)" if s.get("choice_group") else ""
                lines.append(f"      {label}: " + "; ".join(bits) + alt + ".")

    printed, evaluation = template_totals(tdef)
    return (
        "PAPER STRUCTURE — reproduce it EXACTLY. Write one question for EVERY "
        "position listed below, in this order. Optional and either/or questions "
        "must ALL be written. Do not add, merge, drop or reorder anything:"
        + "".join(lines)
        + f"\n\nTotal questions to write: {len(specs)}. "
        f"Printed total (every question shown): {_fmt(printed)} marks. "
        f"Evaluation total (maximum a student can score): {_fmt(evaluation)} marks."
    )
