"""
M06 AST Similarity — cross-cohort code plagiarism detection.

Approach:
  1. Parse each submission to AST.
  2. Normalise the AST (remove docstrings, rename variables to generic names,
     strip comments) → canonical string via ast.dump().
  3. Compute character n-gram TF-IDF cosine similarity between the target
     and each cohort member's canonical AST string.

Falls back to raw token similarity if AST parsing fails (SyntaxError).

Returns ASTSimilarityResult with:
  max_similarity: float
  matches: [{submission_id, similarity}] — top-3
  is_flagged: bool (max_similarity >= threshold)
"""
from __future__ import annotations

import ast
import dataclasses
import logging
from uuid import UUID

from app.modules.m06_labs_evaluator.plagiarism import (
    PlagiarismResult,
    compute_plagiarism,
)

logger = logging.getLogger("vidya.m06.ast_similarity")


# ---------------------------------------------------------------------------
# AST normalisation
# ---------------------------------------------------------------------------

class _Normaliser(ast.NodeTransformer):
    """
    Rename all Name identifiers to generic tokens (v0, v1, …) so
    renaming variables doesn't evade detection.

    Also removes docstrings and type annotations.
    """

    def __init__(self) -> None:
        self._name_map: dict[str, str] = {}
        self._counter = 0

    def _canonical_name(self, name: str) -> str:
        if name not in self._name_map:
            self._name_map[name] = f"v{self._counter}"
            self._counter += 1
        return self._name_map[name]

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = self._canonical_name(node.id)
        return self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = self._canonical_name(node.arg)
        node.annotation = None
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        # Strip docstring
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:]
        node.returns = None
        return self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]


def _canonical_ast(code: str) -> str | None:
    """
    Returns a canonical string representation of the code's AST.
    Returns None if the code has a SyntaxError.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    try:
        normalised = _Normaliser().visit(tree)
        return ast.dump(normalised, indent=None)
    except Exception as exc:
        logger.debug("AST normalisation failed: %s", exc)
        return ast.dump(tree, indent=None)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_ast_similarity(
    target_code: str,
    cohort: list[tuple[UUID, str]],     # [(submission_id, code), ...]
    *,
    threshold: float = 0.85,
    student_ids: dict[UUID, UUID] | None = None,
) -> PlagiarismResult:
    """
    Compare `target_code` against `cohort` using AST normalisation + cosine similarity.

    Falls back to raw text comparison when AST parsing fails.
    Reuses `compute_plagiarism()` for the similarity computation.
    """
    target_canonical = _canonical_ast(target_code) or target_code

    cohort_canonical: list[tuple[UUID, str]] = []
    for sub_id, code in cohort:
        canon = _canonical_ast(code) or code
        cohort_canonical.append((sub_id, canon))

    return compute_plagiarism(
        target_canonical,
        cohort_canonical,
        threshold=threshold,
        student_ids=student_ids,
    )
