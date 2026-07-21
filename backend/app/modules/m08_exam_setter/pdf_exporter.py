"""
M08 Exam Setter — ReportLab PDF exporter.

Generates a print-ready exam paper PDF. Model answers are never included.
"""
from __future__ import annotations

import io
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.modules.m08_exam_setter.paper_template import (
    ANY_K,
    _sid as template_sid,
    has_template,
    normalise_definition,
    section_totals,
    section_weights,
    template_totals,
)

PAGE_W, PAGE_H = A4
MARGIN = 2.0 * cm
CONTENT_W = PAGE_W - 2 * MARGIN
MARKS_COL = 1.5 * cm
TEXT_COL = CONTENT_W - MARKS_COL

_BASE = getSampleStyleSheet()


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "institution": ParagraphStyle(
            "institution", parent=_BASE["Normal"],
            fontSize=14, leading=18, alignment=TA_CENTER,
            fontName="Helvetica-Bold", spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=_BASE["Normal"],
            fontSize=10, alignment=TA_CENTER, spaceAfter=2,
        ),
        "exam_title": ParagraphStyle(
            "exam_title", parent=_BASE["Normal"],
            fontSize=12, leading=16, alignment=TA_CENTER,
            fontName="Helvetica-Bold", spaceBefore=4, spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "meta", parent=_BASE["Normal"],
            fontSize=9, alignment=TA_CENTER,
        ),
        "instr_head": ParagraphStyle(
            "instr_head", parent=_BASE["Normal"],
            fontSize=9, fontName="Helvetica-Bold",
        ),
        "instr_body": ParagraphStyle(
            "instr_body", parent=_BASE["Normal"],
            fontSize=9, leftIndent=12,
        ),
        "sec_header": ParagraphStyle(
            "sec_header", parent=_BASE["Normal"],
            fontSize=10, fontName="Helvetica-Bold",
            spaceBefore=10, spaceAfter=2,
        ),
        "sec_instr": ParagraphStyle(
            "sec_instr", parent=_BASE["Normal"],
            fontSize=9, fontName="Helvetica-Oblique", spaceAfter=4,
        ),
        "fullq_head": ParagraphStyle(
            "fullq_head", parent=_BASE["Normal"],
            fontSize=10.5, leading=14, fontName="Helvetica-Bold",
            spaceBefore=10, spaceAfter=3,
        ),
        "question": ParagraphStyle(
            "question", parent=_BASE["Normal"],
            fontSize=10, leading=14,
        ),
        "marks": ParagraphStyle(
            "marks", parent=_BASE["Normal"],
            fontSize=10, leading=14, alignment=TA_RIGHT,
            fontName="Helvetica-Bold",
        ),
        "or_sep": ParagraphStyle(
            "or_sep", parent=_BASE["Normal"],
            fontSize=9, alignment=TA_CENTER,
            fontName="Helvetica-Oblique",
            spaceBefore=3, spaceAfter=3,
        ),
        "option": ParagraphStyle(
            "option", parent=_BASE["Normal"],
            fontSize=9, leading=13, leftIndent=24,
        ),
    }


def _on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(
        PAGE_W / 2, MARGIN * 0.35,
        f"Page {doc.page}   |   Confidential — Exam Copy",
    )
    canvas.restoreState()


def generate_exam_pdf(
    paper: Any,
    questions: list[Any],
    course: Optional[Any] = None,
    set_label: str = "A",
) -> bytes:
    """
    Build a print-ready exam paper PDF and return the bytes.

    paper     : ExamPaper ORM instance
    questions : list[ExamQuestion] (no model answers)
    course    : optional Course ORM instance for code/title display
    set_label : shown in header when paper has multiple sets
    """
    buf = io.BytesIO()
    st  = _styles()

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN + 0.6 * cm,
        title=paper.title,
    )

    frame = Frame(
        MARGIN,
        MARGIN + 0.6 * cm,
        CONTENT_W,
        PAGE_H - 2 * MARGIN - 0.6 * cm,
        id="body",
    )
    doc.addPageTemplates([PageTemplate("main", [frame], onPage=_on_page)])

    story: list = []

    # -----------------------------------------------------------------------
    # Header block
    # -----------------------------------------------------------------------
    story.append(Paragraph("UNIVERSITY EXAMINATION", st["institution"]))

    if course:
        story.append(Paragraph(f"{course.code} — {course.title}", st["subtitle"]))

    story.append(Paragraph(paper.title, st["exam_title"]))
    story.append(Paragraph(paper.exam_type.replace("_", " ").title(), st["subtitle"]))

    story.append(
        HRFlowable(width="100%", thickness=1.5, color=colors.black, spaceAfter=4)
    )

    # Metadata bar: Duration | Total Marks | Date
    dur_h = paper.duration_mins // 60
    dur_m = paper.duration_mins % 60
    dur_str = (
        f"{dur_h} hr {dur_m} min" if dur_m
        else f"{dur_h} {'Hours' if dur_h > 1 else 'Hour'}"
    )

    # Two totals for university patterns: Printed (all generated) vs Max/Evaluation
    # (what a student can score). The template owns them when there is one — it is
    # the only thing that knows about choice groups. Legacy papers fall back to the
    # blueprint, then to a single Total Marks.
    blueprint = getattr(paper, "blueprint", None)
    if has_template(paper):
        printed_total, eval_total = template_totals(paper.template_definition)
    elif blueprint:
        printed_total, eval_total = _blueprint_totals(blueprint)
    else:
        printed_total, eval_total = None, None
    if printed_total:
        marks_cell = Paragraph(
            f"<b>Max Marks:</b> {_fmt_num(eval_total)} &nbsp;|&nbsp; "
            f"<b>Printed:</b> {_fmt_num(printed_total)}",
            st["meta"],
        )
    else:
        marks_cell = Paragraph(f"<b>Total Marks:</b> {paper.total_marks}", st["meta"])

    col = CONTENT_W / 3
    meta_row = [[
        Paragraph(f"<b>Duration:</b> {dur_str}", st["meta"]),
        marks_cell,
        Paragraph("<b>Date:</b> _______________", st["meta"]),
    ]]
    meta_tbl = Table(meta_row, colWidths=[col, col, col])
    meta_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meta_tbl)
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=4, spaceAfter=6))

    # -----------------------------------------------------------------------
    # Instructions
    # -----------------------------------------------------------------------
    story.append(Paragraph("INSTRUCTIONS:", st["instr_head"]))

    instructions: list[str] = []
    if paper.section_config:
        instructions.append("This paper is divided into sections. Read each section instruction carefully.")
    if paper.special_instructions:
        for ln in paper.special_instructions.strip().splitlines():
            ln = ln.strip()
            if ln:
                instructions.append(ln)
    if not instructions:
        instructions = [
            "Answer all questions unless the section instructs otherwise.",
            "Write clearly and legibly.",
            "Mobile phones and electronic devices are not permitted in the examination hall.",
        ]

    for i, txt in enumerate(instructions, 1):
        story.append(Paragraph(f"{i}. {txt}", st["instr_body"]))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=8))

    # -----------------------------------------------------------------------
    # Questions — section-based or flat
    # -----------------------------------------------------------------------
    q_num = 1

    if paper.section_config and len(paper.section_config) > 0:
        sections = sorted(paper.section_config, key=lambda s: s.get("order", 0))
        by_section: dict[str, list[Any]] = {}
        for q in questions:
            by_section.setdefault(q.section_label or "—", []).append(q)

        for sec in sections:
            lbl       = sec["label"]
            sec_qs    = by_section.get(lbl, [])
            if not sec_qs:
                continue

            total_q    = sec.get("total_q", len(sec_qs))
            answer_q   = sec.get("answer_q", total_q)
            marks_each = float(sec.get("marks_each", 0))
            sec_marks  = int(total_q * marks_each)
            instruction = sec.get("instruction") or ""

            marks_label = int(marks_each) if marks_each == int(marks_each) else marks_each
            story.append(Paragraph(
                f"SECTION {lbl}  ({total_q} \xd7 {marks_label} = {sec_marks} Marks)",
                st["sec_header"],
            ))

            if answer_q < total_q:
                story.append(Paragraph(
                    f"Answer any {answer_q} of {total_q} questions.",
                    st["sec_instr"],
                ))
            elif instruction:
                story.append(Paragraph(instruction, st["sec_instr"]))

            q_num = _render_questions(sec_qs, story, st, q_num)
    elif _has_template(paper):
        # Paper Template is the source of truth: render Sections / Full Questions
        # exactly as configured. Falls back internally to blueprint for leftovers.
        q_num = _render_template(paper, questions, story, st, q_num)
    elif blueprint:
        q_num = _render_blueprint(paper, questions, story, st, q_num)
    else:
        q_num = _render_questions(questions, story, st, q_num)

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Blueprint helpers (university exam patterns)
# ---------------------------------------------------------------------------

_NUM_WORDS = {
    1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX", 7: "SEVEN",
    8: "EIGHT", 9: "NINE", 10: "TEN", 11: "ELEVEN", 12: "TWELVE",
    13: "THIRTEEN", 14: "FOURTEEN", 15: "FIFTEEN", 16: "SIXTEEN",
    17: "SEVENTEEN", 18: "EIGHTEEN", 19: "NINETEEN", 20: "TWENTY",
}


def _num_word(n: int) -> str:
    return _NUM_WORDS.get(int(n), str(int(n)))


def _fmt_num(v: Any) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


def _blueprint_totals(blueprint: Any) -> tuple[float, float]:
    """Return (printed_total, evaluation_total) from a paper blueprint.

    printed    = sum(count × marks)                 — all generated questions.
    evaluation = sum(min(answer_count, count) × marks) — maximum a student scores.
    Legacy rows without answer_count default answer_count == count, so both
    totals equal the previous single total (backward compatible).
    """
    printed = 0.0
    evaluation = 0.0
    for entry in (blueprint or []):
        for row in (entry.get("rows") or []):
            count = int(row.get("count") or 0)
            marks = float(row.get("marks") or 0)
            if count <= 0 or marks <= 0:
                continue
            answer = int(row.get("answer_count") or count)
            answer = min(answer, count)
            printed += count * marks
            evaluation += answer * marks
    return printed, evaluation


def _render_blueprint(paper: Any, questions: list, story: list, st: dict, q_num: int) -> int:
    """Render questions grouped by blueprint rows, printing the choice instruction
    for each group. Questions generated from P1.17 onward carry the id of the
    blueprint row that produced them, so each group is an exact lookup; older
    papers fall back to matching by (unit, marks) in document order and render
    anything left over flat under 'Additional Questions'.

    Rows print in the faculty's block order — the blueprint stores them grouped by
    unit, so block_order is what restores the paper's real layout.
    """
    used = [False] * len(questions)
    by_block: dict[str, list] = {}
    for q in questions:
        bid = getattr(q, "template_block_id", None)
        if bid:
            by_block.setdefault(str(bid), []).append(q)

    ordered_rows: list[tuple] = []
    for entry in (paper.blueprint or []):
        try:
            unit_no = int(entry.get("unit_number"))
        except (TypeError, ValueError):
            unit_no = None
        for row in (entry.get("rows") or []):
            bo = row.get("block_order")
            ordered_rows.append((10_000 if bo is None else int(bo), len(ordered_rows), unit_no, row))
    ordered_rows.sort(key=lambda r: (r[0], r[1]))

    for _bo, _seq, unit_no, row in ordered_rows:
        count = int(row.get("count") or 0)
        marks = float(row.get("marks") or 0)
        if count <= 0 or marks <= 0:
            continue
        answer   = min(int(row.get("answer_count") or count), count)
        pattern  = (row.get("choice_pattern") or "COMPULSORY").upper()
        category = (row.get("category") or "").strip()

        grp: list = []
        row_bid = row.get("template_block_id")
        if row_bid and str(row_bid) in by_block:
            grp = by_block[str(row_bid)][:count]
            grp_ids = {id(q) for q in grp}
            for i, q in enumerate(questions):
                if id(q) in grp_ids:
                    used[i] = True
        else:
            for i, q in enumerate(questions):
                if used[i]:
                    continue
                if unit_no is not None and int(getattr(q, "unit_number", -1)) != unit_no:
                    continue
                if float(q.marks) != marks:
                    continue
                grp.append(q)
                used[i] = True
                if len(grp) >= count:
                    break
        if not grp:
            continue

        n = len(grp)
        header = f"Unit {unit_no}" if unit_no is not None else "Questions"
        if category:
            header += f" — {category}"
        header += f"  ({n} \xd7 {_fmt_num(marks)} = {_fmt_num(n * marks)} Marks)"
        story.append(Paragraph(header, st["sec_header"]))

        if pattern == "OR_CHOICE" and n > 1:
            elems: list = []
            for i, q in enumerate(grp):
                if i > 0:
                    elems.append(Paragraph("— OR —", st["or_sep"]))
                elems.extend(_question_elems(q, q_num, st))
                q_num += 1
            story.append(KeepTogether(elems))
        else:
            if answer < n:
                plural = "s" if answer != 1 else ""
                story.append(Paragraph(
                    f"Answer any {_num_word(answer)} question{plural}.",
                    st["sec_instr"],
                ))
            for q in grp:
                story.append(KeepTogether(_question_elems(q, q_num, st)))
                q_num += 1

    leftover = [q for i, q in enumerate(questions) if not used[i]]
    if leftover and by_block:
        # These questions know which row owns them, so a leftover means the paper
        # and its blueprint have diverged. Bucketing it would print a paper that is
        # not the one the faculty configured.
        raise ValueError(
            f"Paper {getattr(paper, 'id', '?')} cannot be reconstructed from its "
            f"blueprint: {len(leftover)} question(s) belong to no blueprint row."
        )
    if leftover:
        story.append(Paragraph("Additional Questions", st["sec_header"]))
        q_num = _render_questions(leftover, story, st, q_num)

    return q_num


# ---------------------------------------------------------------------------
# Template rendering — Section / Full Question / Hybrid (source of truth)
# ---------------------------------------------------------------------------

def _has_template(paper: Any) -> bool:
    return has_template(paper)


def _section_header(name: str) -> str:
    """"A" -> "SECTION A"; "Part A" -> "PART A". Faculty type whatever their
    university calls it, and it prints once, not doubled."""
    n = (name or "").strip()
    if not n:
        return "SECTION"
    if n.upper().startswith(("SECTION", "PART", "MODULE", "UNIT", "GROUP")):
        return n.upper()
    return f"SECTION {n.upper()}"


def _definition_shape(qd: dict) -> list[dict]:
    """The printed questions ONE definition contributes, in emission order.

    This mirrors compile_specs exactly — that is the whole point. A spec is
    emitted per (repetition x part x alternative), so walking this shape over a
    definition's questions in order reconstructs the paper without ever guessing
    from marks or units.

    Each entry is one PRINTED question (what a number is spent on, and what an
    answer rule counts):

        {"alts": 2, "marks": 6.0, "parts": None}     a 6-mark either/or
        {"parts": [{"index": 0, "alts": 1, "marks": 8.0}, ...]}   "Q1 a) b)"
    """
    parts = qd.get("parts") or []
    count = max(0, int(qd.get("count") or 0))
    shape: list[dict] = []

    for _n in range(count):
        if not parts:
            marks = float(qd.get("marks") or 0)
            if marks <= 0:
                continue
            shape.append({
                "parts": None,
                "alts":  2 if qd.get("or_choice") else 1,
                "marks": marks,
            })
            continue

        entries: list[dict] = []
        for pi, part in enumerate(parts):
            pmarks = float(part.get("marks") or 0)
            if pmarks <= 0:
                continue
            entries.append({
                "index": pi,
                "alts":  2 if part.get("or_choice") else 1,
                "marks": pmarks,
            })
        if entries:
            shape.append({"parts": entries})

    return shape


def _section_rule_text(sec: dict) -> str:
    """The instruction a section prints. The faculty's own words win; otherwise the
    answer rule says it, in the words a paper actually uses."""
    instr = (sec.get("instruction") or "").strip()
    if instr:
        return instr
    ws = section_weights(sec)
    rule = sec.get("answer_rule") or {}
    if (rule.get("mode") or "ALL").upper() == ANY_K:
        k = max(0, min(int(rule.get("k") or len(ws)), len(ws)))
        return (f"Answer any {_num_word(k)} of the following "
                f"{_num_word(len(ws))} question{'s' if len(ws) != 1 else ''}.")
    return "Answer ALL questions."


def _render_template(paper: Any, questions: list, story: list, st: dict, q_num: int) -> int:
    """Render a paper from its template — the source of truth for its structure.

    The template is Sections of Question Definitions, and nothing else. A section
    prints a header and its rule; a definition contributes the questions it asked
    for. Every question carries the id of the DEFINITION it was generated for, so
    each definition is an exact lookup and every question prints in exactly one
    place. There is no "additional questions" bucket, and numbering follows the
    printed order of the template rather than the order questions happened to be
    generated.

    Nothing here knows a university's name. "Answer any FIVE of EIGHT", "Q1 a) b)
    c)", "answer one of each OR pair" are all just sections, rules and
    definitions.

    Papers generated before P1.17 carry no definition ids and fall back to (unit,
    marks) inference.
    """
    doc = normalise_definition(getattr(paper, "template_definition", None))
    sections = doc["sections"]

    if not any(getattr(q, "template_block_id", None) for q in questions):
        return _render_template_inferred(paper, questions, story, st, q_num)

    by_def: dict[str, list] = {}
    for q in questions:
        by_def.setdefault(str(getattr(q, "template_block_id", "") or ""), []).append(q)

    known = {
        template_sid(qd, "qd", di)
        for sec in sections
        for di, qd in enumerate(sec.get("definitions") or [])
    }
    orphans = sorted(set(by_def) - known)
    if orphans:
        # A question that belongs to no definition means the paper and its
        # template have diverged. Surfacing it is the point: silently bucketing it
        # would print a paper that is not the template the faculty approved.
        raise ValueError(
            f"Paper {getattr(paper, 'id', '?')} cannot be reconstructed from its "
            f"template: {sum(len(by_def[o]) for o in orphans)} question(s) reference "
            f"unknown template definition(s) {orphans}. "
            f"Template definitions: {sorted(known)}."
        )

    for si, sec in enumerate(sections):
        defs = sec.get("definitions") or []
        # Skip a section that generated nothing at all rather than print an empty
        # header.
        if not any(by_def.get(template_sid(qd, "qd", di)) for di, qd in enumerate(defs)):
            continue

        _printed, evaluation = section_totals(sec)
        header = _section_header(sec.get("name") or "")
        if evaluation > 0:
            header += f"  ({_fmt_num(evaluation)} Marks)"
        story.append(Paragraph(header, st["sec_header"]))
        story.append(Paragraph(_section_rule_text(sec), st["sec_instr"]))

        for di, qd in enumerate(defs):
            qd_id = template_sid(qd, "qd", di)
            pool  = list(by_def.get(qd_id) or [])
            pos   = 0

            def _take(n: int) -> list:
                nonlocal pos
                got = pool[pos:pos + n]
                pos += len(got)
                return got

            for entry in _definition_shape(qd):
                if entry["parts"] is None:
                    qs = _take(entry["alts"])
                    if not qs:
                        continue
                    if len(qs) > 1:
                        # An either/or prints both alternatives under one number.
                        elems: list = []
                        for i, q in enumerate(qs):
                            if i > 0:
                                elems.append(Paragraph("— OR —", st["or_sep"]))
                            elems.extend(_question_elems(q, q_num, st))
                        story.append(KeepTogether(elems))
                    else:
                        story.append(KeepTogether(_question_elems(qs[0], q_num, st)))
                    q_num += 1
                    continue

                # A full question: "Q1  (12 Marks)" then a) b) c), where a part may
                # itself be an either/or labelled with consecutive letters.
                rendered: list[tuple[list, bool]] = []
                total = 0.0
                for part in entry["parts"]:
                    qs = _take(part["alts"])
                    if not qs:
                        continue
                    total += part["marks"]
                    rendered.append((qs, part["alts"] > 1))
                if not rendered:
                    continue

                elems = [Paragraph(
                    f"<b>Q{q_num}.</b>&nbsp;&nbsp;({_fmt_num(total)} Marks)",
                    st["fullq_head"],
                )]
                letter_i = 0
                for qs, is_or in rendered:
                    elems.extend(_question_elems(
                        qs[0], q_num, st, label=f"{chr(97 + letter_i)})", indent=16
                    ))
                    letter_i += 1
                    if is_or and len(qs) > 1:
                        elems.append(Paragraph("— OR —", st["or_sep"]))
                        elems.extend(_question_elems(
                            qs[1], q_num, st, label=f"{chr(97 + letter_i)})", indent=16
                        ))
                        letter_i += 1
                story.append(KeepTogether(elems))
                q_num += 1

    return q_num


def _render_template_inferred(paper: Any, questions: list, story: list, st: dict, q_num: int) -> int:
    """Legacy reconstruction for papers generated before P1.17, whose questions
    carry no template definition id.

    Reads the same normalised v3 document as the main path — an old block-based
    document upgrades to one section per block, which is exactly what those papers
    already printed — and matches questions by (unit, marks) in document order.
    Anything left over renders flat rather than being dropped.
    """
    doc = normalise_definition(getattr(paper, "template_definition", None))
    used = [False] * len(questions)

    def take(unit: Any, marks: float, n: int) -> list:
        got: list = []
        for i, q in enumerate(questions):
            if used[i]:
                continue
            if unit is not None and int(getattr(q, "unit_number", -1)) != int(unit):
                continue
            if float(q.marks) != float(marks):
                continue
            got.append(q)
            used[i] = True
            if len(got) >= n:
                break
        return got

    for sec in doc["sections"]:
        defs = sec.get("definitions") or []
        pending: list = []

        for qd in defs:
            units = qd.get("units") or []
            # An upgraded legacy block carried exactly one unit; a pool of one is
            # that unit, and an empty pool matches on marks alone.
            unit = units[0] if len(units) == 1 else None

            for entry in _definition_shape(qd):
                if entry["parts"] is None:
                    qs = take(unit, entry["marks"], entry["alts"])
                    if qs:
                        pending.append((qs, entry["alts"] > 1, None))
                    continue
                for part in entry["parts"]:
                    qs = take(unit, part["marks"], part["alts"])
                    if qs:
                        pending.append((qs, part["alts"] > 1, part["marks"]))

        if not pending:
            continue

        _printed, evaluation = section_totals(sec)
        header = _section_header(sec.get("name") or "")
        if evaluation > 0:
            header += f"  ({_fmt_num(evaluation)} Marks)"
        story.append(Paragraph(header, st["sec_header"]))
        story.append(Paragraph(_section_rule_text(sec), st["sec_instr"]))

        for qs, is_or, _m in pending:
            if is_or and len(qs) > 1:
                elems: list = []
                for i, q in enumerate(qs):
                    if i > 0:
                        elems.append(Paragraph("— OR —", st["or_sep"]))
                    elems.extend(_question_elems(q, q_num, st))
                story.append(KeepTogether(elems))
            else:
                story.append(KeepTogether(_question_elems(qs[0], q_num, st)))
            q_num += 1

    leftover = [q for i, q in enumerate(questions) if not used[i]]
    if leftover:
        story.append(Paragraph("ADDITIONAL QUESTIONS", st["sec_header"]))
        for q in leftover:
            story.append(KeepTogether(_question_elems(q, q_num, st)))
            q_num += 1

    return q_num


def _render_questions(
    questions: list[Any],
    story: list,
    st: dict,
    q_num: int,
) -> int:
    """Render questions; group consecutive same-choice_group as OR alternatives."""
    groups: list[tuple] = []
    cur_group: Optional[int] = None
    cur_qs: list[Any] = []

    for q in questions:
        cg = q.choice_group
        if cg is not None and cg == cur_group:
            cur_qs.append(q)
        else:
            if cur_qs:
                groups.append((cur_group, cur_qs))
            cur_group = cg
            cur_qs = [q]
    if cur_qs:
        groups.append((cur_group, cur_qs))

    for grp_id, grp_qs in groups:
        if grp_id is None or len(grp_qs) == 1:
            for q in grp_qs:
                story.append(KeepTogether(_question_elems(q, q_num, st)))
                q_num += 1
        else:
            elems: list = []
            for i, q in enumerate(grp_qs):
                if i > 0:
                    elems.append(Paragraph("— OR —", st["or_sep"]))
                elems.extend(_question_elems(q, q_num, st))
                q_num += 1
            story.append(KeepTogether(elems))

    return q_num


def _question_elems(q: Any, q_num: int, st: dict, label: str | None = None, indent: float = 0.0) -> list:
    """Return a list of flowables for one question (not wrapped in KeepTogether).

    label  — lead marker; defaults to "{q_num}." A Full-Question sub-part passes
             e.g. "a)". indent — left padding (points) for nested sub-parts.
    """
    marks_val = float(q.marks)
    marks_str = str(int(marks_val)) if marks_val == int(marks_val) else str(marks_val)

    lead = label if label is not None else f"{q_num}."
    q_para = Paragraph(f"<b>{lead}</b>  {q.question_text}", st["question"])
    m_para = Paragraph(f"[{marks_str}]", st["marks"])

    tbl = Table([[q_para, m_para]], colWidths=[TEXT_COL, MARKS_COL])
    tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (0, 0),   indent),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 0),
    ]))

    elems: list = [tbl]

    if q.question_type == "MCQ" and q.options:
        for opt in q.options:
            label = opt.get("label", "")
            text  = opt.get("text", "")
            elems.append(Paragraph(f"({label}) \xa0 {text}", st["option"]))

    elems.append(Spacer(1, 5))
    return elems
