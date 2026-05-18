"""
M07 Novelty Search — arXiv literature search + TF-IDF novelty scoring.

Given a research problem title, abstract, and research questions:
  1. Build a combined query string.
  2. Search arXiv API for the top-N most relevant papers.
  3. Compute TF-IDF cosine similarity between the query and each paper abstract.
  4. Novelty score = 1 - max_similarity (higher = more novel / fewer exact matches).

Graceful degradation: if arXiv is unreachable or times out, returns
  novelty_score=0.5, papers=[], error=<message>
so the pipeline never blocks on external API availability.
"""
from __future__ import annotations

import dataclasses
import logging
import math
import re
import urllib.parse
import urllib.request
from xml.etree import ElementTree

logger = logging.getLogger("vidya.m07.novelty_search")

_ARXIV_API = "https://export.arxiv.org/api/query"
_ATOM_NS   = "http://www.w3.org/2005/Atom"


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ArxivPaper:
    arxiv_id: str
    title:    str
    abstract: str
    authors:  list[str]
    url:      str


@dataclasses.dataclass
class NoveltyResult:
    novelty_score:    float          # 0–1; higher = more novel
    max_similarity:   float          # similarity to most related paper
    papers:           list[ArxivPaper]
    query_used:       str
    error:            str | None


# ---------------------------------------------------------------------------
# TF-IDF helpers (zero external deps)
# ---------------------------------------------------------------------------

_STOP = frozenset(
    "a an the and or in of to for with on at by from is are was were be been "
    "that this it its as but not all can will would could should have has had "
    "do does did may might must shall how what when where who which why".split()
)


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOP and len(w) > 2]


def _tf(tokens: list[str]) -> dict[str, float]:
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    total = len(tokens) or 1
    return {t: c / total for t, c in freq.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# arXiv API query
# ---------------------------------------------------------------------------

def _arxiv_search(query: str, max_results: int, timeout: float = 10.0) -> list[ArxivPaper]:
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start":         0,
        "max_results":   max_results,
        "sortBy":        "relevance",
        "sortOrder":     "descending",
    })
    url = f"{_ARXIV_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vidya-Research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()

    root = ElementTree.fromstring(content)
    papers: list[ArxivPaper] = []
    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        arxiv_id_el = entry.find(f"{{{_ATOM_NS}}}id")
        title_el    = entry.find(f"{{{_ATOM_NS}}}title")
        summary_el  = entry.find(f"{{{_ATOM_NS}}}summary")
        if arxiv_id_el is None or title_el is None or summary_el is None:
            continue
        arxiv_url = (arxiv_id_el.text or "").strip()
        title     = re.sub(r"\s+", " ", (title_el.text or "")).strip()
        abstract  = re.sub(r"\s+", " ", (summary_el.text or "")).strip()
        authors = [
            (a.find(f"{{{_ATOM_NS}}}name") or type("", (), {"text": ""})()).text or ""
            for a in entry.findall(f"{{{_ATOM_NS}}}author")
        ]
        papers.append(ArxivPaper(
            arxiv_id=arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else arxiv_url,
            title=title,
            abstract=abstract,
            authors=[a for a in authors if a],
            url=arxiv_url,
        ))
    return papers


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_novelty(
    title: str,
    abstract: str,
    research_questions: list[str],
    *,
    max_results: int = 10,
    timeout: float = 10.0,
) -> NoveltyResult:
    """
    Score how novel the research problem is against arXiv literature.
    Returns novelty_score in [0, 1].
    0 = identical to existing work; 1 = completely novel.
    """
    # Build a concise query: title + first 100 chars of abstract
    query_text = title
    if abstract:
        query_text += " " + abstract[:100]
    query_text = re.sub(r"\s+", " ", query_text).strip()[:200]

    try:
        papers = _arxiv_search(query_text, max_results=max_results, timeout=timeout)
    except Exception as exc:
        logger.warning("arXiv search failed: %s", exc)
        return NoveltyResult(
            novelty_score=0.5,
            max_similarity=0.0,
            papers=[],
            query_used=query_text,
            error=str(exc),
        )

    if not papers:
        return NoveltyResult(
            novelty_score=0.8,
            max_similarity=0.0,
            papers=[],
            query_used=query_text,
            error=None,
        )

    # Query TF vector
    query_tokens = _tokenize(f"{title} {abstract} {' '.join(research_questions)}")
    query_tf = _tf(query_tokens)

    max_sim = 0.0
    for paper in papers:
        paper_tokens = _tokenize(f"{paper.title} {paper.abstract}")
        paper_tf = _tf(paper_tokens)
        sim = _cosine(query_tf, paper_tf)
        if sim > max_sim:
            max_sim = sim

    novelty = max(0.0, min(1.0, 1.0 - max_sim))
    return NoveltyResult(
        novelty_score=round(novelty, 3),
        max_similarity=round(max_sim, 3),
        papers=papers[:max_results],
        query_used=query_text,
        error=None,
    )
