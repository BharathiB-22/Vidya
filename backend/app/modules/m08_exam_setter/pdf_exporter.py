"""
M08 Exam Setter — ReportLab PDF exporter.

Generates a print-ready exam paper PDF. Model answers are never included.
"""
from __future__ import annotations

import io
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
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

    col = CONTENT_W / 3
    meta_row = [[
        Paragraph(f"<b>Duration:</b> {dur_str}", st["meta"]),
        Paragraph(f"<b>Total Marks:</b> {paper.total_marks}", st["meta"]),
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
    else:
        q_num = _render_questions(questions, story, st, q_num)

    doc.build(story)
    return buf.getvalue()


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


def _question_elems(q: Any, q_num: int, st: dict) -> list:
    """Return a list of flowables for one question (not wrapped in KeepTogether)."""
    marks_val = float(q.marks)
    marks_str = str(int(marks_val)) if marks_val == int(marks_val) else str(marks_val)

    q_para = Paragraph(f"<b>{q_num}.</b>  {q.question_text}", st["question"])
    m_para = Paragraph(f"[{marks_str}]", st["marks"])

    tbl = Table([[q_para, m_para]], colWidths=[TEXT_COL, MARKS_COL])
    tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (0, 0),   0),
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
