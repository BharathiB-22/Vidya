"""
M06 Static Analyser — complexity + issue detection for Python code.

Uses:
  - ast module (stdlib): parse-time error detection, unused name walk
  - radon (pip package): cyclomatic complexity per function
  - pyflakes (pip package): unused imports, undefined names

Returns StaticAnalysisResult with:
  complexity_score: int (highest McCabe complexity found across all functions)
  complexity_label: str (A=1, B=2-3, C=4-5, D=6-9, E=10-14, F=15+)
  issues: [{line, message, code}] — unused imports, syntax errors, etc.

Gracefully handles missing radon/pyflakes (returns minimal result).
"""
from __future__ import annotations

import ast
import dataclasses
import logging

logger = logging.getLogger("vidya.m06.static_analyser")

_COMPLEXITY_LABELS = {
    range(1, 2):   "A",
    range(2, 4):   "B",
    range(4, 6):   "C",
    range(6, 10):  "D",
    range(10, 15): "E",
    range(15, 9999): "F",
}


def _label_for_score(score: int) -> str:
    for r, label in _COMPLEXITY_LABELS.items():
        if score in r:
            return label
    return "F"


@dataclasses.dataclass
class StaticAnalysisResult:
    complexity_score: int
    complexity_label: str
    issues: list[dict]     # [{line, message, code}]
    parse_error: str | None = None


# ---------------------------------------------------------------------------
# Complexity via radon
# ---------------------------------------------------------------------------

def _radon_complexity(code: str) -> int:
    """Return max cyclomatic complexity across all functions. 0 if radon absent."""
    try:
        from radon.complexity import cc_visit  # type: ignore[import]
        blocks = cc_visit(code)
        if not blocks:
            return 1
        return max(b.complexity for b in blocks)
    except SyntaxError:
        return 0
    except ImportError:
        logger.debug("radon not installed; skipping complexity analysis.")
        return 1
    except Exception as exc:
        logger.debug("radon error: %s", exc)
        return 1


# ---------------------------------------------------------------------------
# Unused imports / undefined names via pyflakes
# ---------------------------------------------------------------------------

def _pyflakes_issues(code: str) -> list[dict]:
    """Return list of pyflakes messages as {line, message, code}."""
    try:
        from pyflakes import api as pf_api  # type: ignore[import]
        from pyflakes import checker as pf_checker  # type: ignore[import]

        pf_api.check(code, "<submission>")
        # pyflakes returns a count; we need to collect messages
        # Use checker directly for structured output
        try:
            tree = compile(code, "<submission>", "exec", ast.PyCF_ONLY_AST)
        except SyntaxError:
            return []

        w = pf_checker.Checker(tree, "<submission>")
        issues = []
        for msg in w.messages:
            issues.append({
                "line": msg.lineno,
                "message": msg.message % msg.message_args,
                "code": type(msg).__name__,
            })
        return issues

    except ImportError:
        logger.debug("pyflakes not installed; skipping issue detection.")
        return []
    except Exception as exc:
        logger.debug("pyflakes error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Syntax check via stdlib ast
# ---------------------------------------------------------------------------

def _syntax_issues(code: str) -> tuple[str | None, list[dict]]:
    """Return (parse_error, issues). parse_error is non-None on SyntaxError."""
    try:
        ast.parse(code)
        return None, []
    except SyntaxError as exc:
        return str(exc), [{
            "line": exc.lineno or 0,
            "message": f"SyntaxError: {exc.msg}",
            "code": "SyntaxError",
        }]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyse(code: str) -> StaticAnalysisResult:
    """
    Run static analysis on `code`.

    Returns StaticAnalysisResult with complexity and issues.
    Never raises — all errors are caught and returned as issues.
    """
    if not code or not code.strip():
        return StaticAnalysisResult(
            complexity_score=0,
            complexity_label="A",
            issues=[],
        )

    parse_error, syntax_issues = _syntax_issues(code)
    if parse_error:
        return StaticAnalysisResult(
            complexity_score=0,
            complexity_label="A",
            issues=syntax_issues,
            parse_error=parse_error,
        )

    complexity = _radon_complexity(code)
    pf_issues  = _pyflakes_issues(code)

    return StaticAnalysisResult(
        complexity_score=complexity,
        complexity_label=_label_for_score(complexity),
        issues=pf_issues,
    )
