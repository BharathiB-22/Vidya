"""
M10 Bell Curve Normaliser — Fairness Report Builder.

Produces a multi-section PDF (reportlab) summarising:
  1. Cover page
  2. Executive Summary
  3. Per-Paper Score Table
  4. Distribution Detail (raw stats + histogram)
  5. Anomaly Detail
  6. Board Decision & Normalisation
  7. Normalised vs Raw Score Comparison
  8. Audit Metadata

Pure computation — no DB access.  Caller supplies pre-fetched ORM objects.
Writes directly to the supplied BytesIO buffer (no return value).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def generate_fairness_pdf(
    buf,
    *,
    analyses:      list,
    decisions_map: dict,
) -> None:
    """
    Write a PDF fairness report to buf (BytesIO).

    analyses:     list of BellCurveAnalysis ORM objects
    decisions_map: {str(analysis_id): BellCurveDecision ORM object}
    """
    now_label = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    template = PageTemplate(id="main", frames=[frame], onPage=_page_footer)
    doc.addPageTemplates([template])

    styles = _build_styles()
    story  = []

    # 1. Cover
    story += _section_cover(styles, now_label)
    story.append(PageBreak())

    # 2. Executive Summary
    story += _section_executive_summary(styles, analyses, decisions_map)
    story.append(PageBreak())

    # 3. Per-paper table
    story += _section_per_paper_table(styles, analyses, decisions_map)
    story.append(PageBreak())

    for analysis in analyses:
        decision = decisions_map.get(str(analysis.id))

        # 4. Distribution detail
        story += _section_distribution(styles, analysis)
        story.append(Spacer(1, 0.5 * cm))

        # 5. Anomaly detail
        story += _section_anomalies(styles, analysis)
        story.append(Spacer(1, 0.5 * cm))

        # 6. Board decision
        story += _section_board_decision(styles, analysis, decision)
        story.append(Spacer(1, 0.5 * cm))

        # 7. Normalised vs raw (only when scores were actually shifted)
        method = getattr(decision, "normalisation_method", None) if decision else None
        if method and method not in ("NONE", "BOUNDARY_SHIFT"):
            story += _section_score_comparison(styles, analysis, decision)
            story.append(Spacer(1, 0.5 * cm))

        story.append(PageBreak())

    # 8. Audit metadata
    story += _section_audit_metadata(styles, analyses)

    doc.build(story)


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _build_styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "title":   ParagraphStyle("title",   parent=ss["Title"],   fontSize=22, spaceAfter=12),
        "h1":      ParagraphStyle("h1",      parent=ss["Heading1"], fontSize=14, spaceAfter=8),
        "h2":      ParagraphStyle("h2",      parent=ss["Heading2"], fontSize=11, spaceAfter=6),
        "body":    ParagraphStyle("body",    parent=ss["Normal"],   fontSize=9,  spaceAfter=4),
        "small":   ParagraphStyle("small",   parent=ss["Normal"],   fontSize=8,  spaceAfter=2),
        "caption": ParagraphStyle("caption", parent=ss["Normal"],   fontSize=8,  textColor=colors.grey),
    }


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(doc.leftMargin, 1.2 * cm, "Vidya — Bell Curve Fairness Report — CONFIDENTIAL")
    canvas.drawRightString(doc.width + doc.leftMargin, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


_TABLE_STYLE = TableStyle([
    ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#2C3E50")),
    ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
    ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
    ("FONTSIZE",      (0, 0), (-1, -1), 8),
    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F3F4")]),
    ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#BDC3C7")),
    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING",    (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ("LEFTPADDING",   (0, 0), (-1, -1), 5),
])


# ---------------------------------------------------------------------------
# Section builders — all access ORM attributes (not dict keys)
# ---------------------------------------------------------------------------

def _section_cover(styles: dict, now_label: str) -> list:
    return [
        Spacer(1, 3 * cm),
        Paragraph("Bell Curve Fairness Report", styles["title"]),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#2C3E50")),
        Spacer(1, 1 * cm),
        Paragraph(f"Generated: {now_label}", styles["body"]),
        Spacer(1, 2 * cm),
        Paragraph(
            "This document is CONFIDENTIAL. It contains statistical analysis of student "
            "score distributions and Board decisions on bell curve normalisation. "
            "Distribution to unauthorised persons is prohibited.",
            styles["small"],
        ),
    ]


def _section_executive_summary(
    styles: dict,
    analyses: list,
    decisions_map: dict,
) -> list:
    total       = len(analyses)
    applied     = sum(1 for a in analyses if _attr(a, "status") == "APPLIED")
    no_action   = sum(1 for a in analyses if _attr(a, "status") == "NO_ACTION")
    pending     = total - applied - no_action
    total_scores = sum(_attr(a, "score_count") or 0 for a in analyses)

    rows = [
        ["Metric", "Value"],
        ["Total exam papers analysed",     str(total)],
        ["Normalisation applied",          str(applied)],
        ["Board decided no-action",        str(no_action)],
        ["Pending / in-progress",          str(pending)],
        ["Total student scores processed", str(total_scores)],
    ]
    return [
        Paragraph("Executive Summary", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7")),
        Spacer(1, 0.3 * cm),
        Table(rows, colWidths=[10 * cm, 5 * cm], style=_TABLE_STYLE),
    ]


def _section_per_paper_table(
    styles: dict,
    analyses: list,
    decisions_map: dict,
) -> list:
    rows = [["Paper ID", "Scores", "Mean", "Std", "Status", "Decision"]]
    for a in analyses:
        rs  = _attr(a, "raw_stats") or {}
        dec = decisions_map.get(str(_attr(a, "id")))
        rows.append([
            _short_id(_attr(a, "exam_paper_id")),
            str(_attr(a, "score_count") or "-"),
            _fmt(rs.get("mean")),
            _fmt(rs.get("std")),
            str(_attr(a, "status") or "-"),
            str(_attr(dec, "decision") or "-") if dec else "-",
        ])
    col_w = [4 * cm, 2 * cm, 2.5 * cm, 2.5 * cm, 3 * cm, 3 * cm]
    return [
        Paragraph("Per-Paper Score Summary", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7")),
        Spacer(1, 0.3 * cm),
        Table(rows, colWidths=col_w, style=_TABLE_STYLE),
    ]


def _section_distribution(styles: dict, analysis) -> list:
    rs  = _attr(analysis, "raw_stats") or {}
    pid = _short_id(_attr(analysis, "exam_paper_id"))

    stat_rows = [
        ["Statistic", "Value"],
        ["Score count", str(_attr(analysis, "score_count") or "-")],
        ["Mean",        _fmt(rs.get("mean"))],
        ["Std dev",     _fmt(rs.get("std"))],
        ["Median",      _fmt(rs.get("median"))],
        ["Min / Max",   f"{_fmt(rs.get('min'))} / {_fmt(rs.get('max'))}"],
        ["Q1 / Q3",     f"{_fmt(rs.get('q1'))} / {_fmt(rs.get('q3'))}"],
        ["Skewness",    _fmt(rs.get("skewness"))],
        ["Kurtosis",    _fmt(rs.get("kurtosis"))],
    ]
    story: list = [
        Paragraph(f"Distribution Detail — Paper {pid}", styles["h2"]),
        Table(stat_rows, colWidths=[5 * cm, 5 * cm], style=_TABLE_STYLE),
    ]

    histogram = rs.get("histogram") or []
    if histogram:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Score Histogram (bin | count | %)", styles["caption"]))
        hist_rows = [["Bin", "Count", "Pct"]]
        for b in histogram:
            hist_rows.append([
                f"{_fmt(b.get('bin_left'))}–{_fmt(b.get('bin_right'))}",
                str(b.get("count", 0)),
                f"{b.get('pct', 0):.1f}%",
            ])
        story.append(
            Table(hist_rows, colWidths=[5 * cm, 2.5 * cm, 2.5 * cm], style=_TABLE_STYLE)
        )
    return story


def _section_anomalies(styles: dict, analysis) -> list:
    anomalies = _attr(analysis, "anomalies") or []
    pid       = _short_id(_attr(analysis, "exam_paper_id"))
    story: list = [Paragraph(f"Anomaly Flags — Paper {pid}", styles["h2"])]
    if not anomalies:
        story.append(Paragraph("No anomalies detected.", styles["body"]))
        return story
    rows = [["Type", "Severity", "Detail"]]
    for a in anomalies:
        rows.append([a.get("type", "-"), a.get("severity", "-"), a.get("detail", "-")])
    story.append(Table(rows, colWidths=[5 * cm, 3 * cm, 9 * cm], style=_TABLE_STYLE))
    return story


def _section_board_decision(styles: dict, analysis, decision) -> list:
    pid   = _short_id(_attr(analysis, "exam_paper_id"))
    story: list = [Paragraph(f"Board Decision — Paper {pid}", styles["h2"])]
    if not decision:
        story.append(Paragraph("No Board decision recorded for this analysis.", styles["body"]))
        return story

    ns = _attr(analysis, "normalisation_suggestion") or {}
    rows = [
        ["Field", "Value"],
        ["Decision",             str(_attr(decision, "decision") or "-")],
        ["Normalisation method", str(_attr(decision, "normalisation_method") or "-")],
        ["Ratified by",          _short_id(_attr(decision, "ratified_by"))],
        ["Ratified at",          _fmt_dt(_attr(decision, "ratified_at"))],
        ["AI suggestion",        ns.get("method", "-")],
        ["Note",                 str(_attr(decision, "ratification_note") or "-")],
    ]
    story.append(Table(rows, colWidths=[5 * cm, 12 * cm], style=_TABLE_STYLE))

    ps = _attr(decision, "projected_stats") or {}
    if ps:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Projected stats after normalisation:", styles["small"]))
        ps_rows = [["Mean", "Std", "Median", "Min", "Max", "Skewness"]]
        ps_rows.append([
            _fmt(ps.get("mean")), _fmt(ps.get("std")), _fmt(ps.get("median")),
            _fmt(ps.get("min")), _fmt(ps.get("max")), _fmt(ps.get("skewness")),
        ])
        story.append(Table(ps_rows, colWidths=[2.8 * cm] * 6, style=_TABLE_STYLE))
    return story


def _section_score_comparison(styles: dict, analysis, decision) -> list:
    pid  = _short_id(_attr(analysis, "exam_paper_id"))
    rs   = _attr(analysis, "raw_stats") or {}
    ps   = _attr(decision, "projected_stats") or {}
    rows = [
        ["Statistic", "Raw",                "Normalised"],
        ["Mean",      _fmt(rs.get("mean")), _fmt(ps.get("mean"))],
        ["Std",       _fmt(rs.get("std")),  _fmt(ps.get("std"))],
        ["Median",    _fmt(rs.get("median")), _fmt(ps.get("median"))],
        ["Min",       _fmt(rs.get("min")),  _fmt(ps.get("min"))],
        ["Max",       _fmt(rs.get("max")),  _fmt(ps.get("max"))],
        ["Skewness",  _fmt(rs.get("skewness")), _fmt(ps.get("skewness"))],
    ]
    return [
        Paragraph(f"Normalised vs Raw Scores — Paper {pid}", styles["h2"]),
        Table(rows, colWidths=[5 * cm, 4 * cm, 4 * cm], style=_TABLE_STYLE),
    ]


def _section_audit_metadata(styles: dict, analyses: list) -> list:
    rows = [["Analysis ID", "Triggered At", "Completed At", "Status"]]
    for a in analyses:
        rows.append([
            _short_id(_attr(a, "id")),
            _fmt_dt(_attr(a, "triggered_at")),
            _fmt_dt(_attr(a, "analysis_completed_at")),
            str(_attr(a, "status") or "-"),
        ])
    col_w = [4 * cm, 5 * cm, 5 * cm, 3 * cm]
    return [
        Paragraph("Audit Metadata", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7")),
        Spacer(1, 0.3 * cm),
        Table(rows, colWidths=col_w, style=_TABLE_STYLE),
        Spacer(1, 0.5 * cm),
        Paragraph(
            "All analysis events are permanently recorded in the Vidya audit log. "
            "Normalised scores are append-only and cannot be modified post-ratification.",
            styles["small"],
        ),
    ]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _attr(obj: Any, name: str) -> Any:
    """Safe attribute access — works for both ORM objects and dicts."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _short_id(val: Any) -> str:
    s = str(val) if val else "-"
    return s[:8] + "…" if len(s) > 12 else s


def _fmt(val: Any) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return str(val)


def _fmt_dt(val: Any) -> str:
    if val is None:
        return "-"
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M")
    return str(val)[:16]
