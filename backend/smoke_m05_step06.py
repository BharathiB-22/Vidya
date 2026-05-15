"""STEP-06 smoke tests -- M05 embedder: cosine similarity, batching, ranking.

No real API calls are made; google-genai client is mocked throughout.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import asyncio
import math
import os

os.environ.setdefault("DATABASE_URL",   "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",      "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",     "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("YOUTUBE_API_KEY","test-yt-key")

from unittest.mock import AsyncMock, MagicMock, patch

import app.config as _cfg
from app.modules.m05_learning_materials.embedder import (
    EmbedderError,
    cosine_similarity,
    embed_texts,
    get_embedder_client,
    score_items,
)
from app.modules.m05_learning_materials.source_adapters.base import RawItem

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        FAIL += 1


def approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) < tol


def approx_lte(a: float, b: float, tol: float = 1e-6) -> bool:
    return a <= b + tol


# ---------------------------------------------------------------------------
# Helpers: mock embed_content response
# ---------------------------------------------------------------------------

class _FakeEmbedding:
    def __init__(self, values: list[float]) -> None:
        self.values = values


class _FakeEmbedResponse:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.embeddings = [_FakeEmbedding(v) for v in vectors]


def _embed_resp(*vectors: list[float]) -> _FakeEmbedResponse:
    return _FakeEmbedResponse(list(vectors))


def _mock_client(embed_side_effect) -> MagicMock:
    """Build a mock google-genai client whose aio.models.embed_content uses side_effect."""
    client = MagicMock()
    client.aio.models.embed_content = AsyncMock(side_effect=embed_side_effect)
    return client


# ===========================================================================
# 1. cosine_similarity — pure math, no mocking
# ===========================================================================
print("\n--- cosine_similarity ---")

check("identical vectors -> 1.0",
      approx(cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]), 1.0))

check("orthogonal vectors -> 0.0",
      approx(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0))

check("opposite vectors clamped to 0.0",
      approx(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), 0.0))

check("zero vector a -> 0.0",
      approx(cosine_similarity([0.0, 0.0], [1.0, 0.0]), 0.0))

check("zero vector b -> 0.0",
      approx(cosine_similarity([1.0, 0.0], [0.0, 0.0]), 0.0))

check("empty vectors -> 0.0",
      approx(cosine_similarity([], []), 0.0))

check("mismatched lengths -> 0.0",
      approx(cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]), 0.0))

# 45-degree angle: cos(45) = 1/sqrt(2) ~ 0.7071
check("45-degree angle",
      approx(cosine_similarity([1.0, 0.0], [1.0, 1.0]), 1.0 / math.sqrt(2), tol=1e-6))

check("result always in [0.0, 1.0] for various vectors",
      all(
          0.0 <= cosine_similarity([a, b], [c, d]) <= 1.0
          for (a, b, c, d) in [
              (1, 0, 1, 0), (1, 0, 0, 1), (1, 0, -1, 0),
              (0.5, 0.5, 0.3, 0.7), (2.0, 3.0, 1.0, 0.5),
          ]
      ))

# ===========================================================================
# 2. embed_texts -- empty input
# ===========================================================================
print("\n--- embed_texts ---")

result = asyncio.run(embed_texts([], tenant_schema="t", package_id="p"))
check("empty input -> [] without calling provider", result == [])

# ===========================================================================
# 3. embed_texts -- single text
# ===========================================================================

v1 = [0.1, 0.2, 0.3]
mock_c = _mock_client([_embed_resp(v1)])
with patch("app.modules.m05_learning_materials.embedder.get_embedder_client",
           return_value=mock_c):
    got = asyncio.run(embed_texts(["hello"], tenant_schema="t", package_id="p"))

check("single text -> 1 vector returned",    len(got) == 1)
check("single text vector values correct",   got[0] == v1)
check("embed_content called once",           mock_c.aio.models.embed_content.call_count == 1)

# ===========================================================================
# 4. embed_texts -- batch splitting (batch_size=2, 5 texts -> 3 API calls)
# ===========================================================================

texts_5 = ["t0", "t1", "t2", "t3", "t4"]
vecs_5  = [[float(i), 0.0] for i in range(5)]

# 3 batches: [t0,t1] -> vecs[0:2], [t2,t3] -> vecs[2:4], [t4] -> vecs[4:5]
side = [
    _embed_resp(vecs_5[0], vecs_5[1]),
    _embed_resp(vecs_5[2], vecs_5[3]),
    _embed_resp(vecs_5[4]),
]
mock_batch = _mock_client(side)

with patch("app.modules.m05_learning_materials.embedder.get_embedder_client",
           return_value=mock_batch):
    with patch.object(_cfg.settings, "M05_EMBED_BATCH_SIZE", 2):
        got5 = asyncio.run(embed_texts(texts_5, tenant_schema="t", package_id="p"))

check("5 texts, batch=2 -> 5 vectors returned",      len(got5) == 5)
check("embed_content called 3 times (ceil(5/2)=3)",
      mock_batch.aio.models.embed_content.call_count == 3)
check("first batch: texts[0:2] sent",
      mock_batch.aio.models.embed_content.call_args_list[0].kwargs["contents"] == ["t0", "t1"])
check("second batch: texts[2:4] sent",
      mock_batch.aio.models.embed_content.call_args_list[1].kwargs["contents"] == ["t2", "t3"])
check("third batch: texts[4:5] sent",
      mock_batch.aio.models.embed_content.call_args_list[2].kwargs["contents"] == ["t4"])
check("vectors are returned in original order",
      got5 == vecs_5)

# ===========================================================================
# 5. embed_texts -- EmbedderError on provider failure
# ===========================================================================

fail_client = _mock_client(Exception("api error"))
with patch("app.modules.m05_learning_materials.embedder.get_embedder_client",
           return_value=fail_client):
    try:
        asyncio.run(embed_texts(["x"], tenant_schema="t", package_id="p"))
        check("EmbedderError raised on provider failure", False)
    except EmbedderError as exc:
        check("EmbedderError raised on provider failure", True)
        check("EmbedderError wraps original message",    "api error" in str(exc))

# ===========================================================================
# 6. score_items -- empty items list
# ===========================================================================
print("\n--- score_items ---")

result_empty = asyncio.run(
    score_items("context", [], tenant_schema="t", package_id="p")
)
check("empty items -> [] without calling provider", result_empty == [])

# ===========================================================================
# 7. score_items -- ranking order
#
#   unit_context vector: [1, 0, 0]
#   item_A: [0.9, 0.1, 0]  -> high similarity
#   item_B: [0.0, 1.0, 0]  -> zero similarity (orthogonal)
#   item_C: [0.5, 0.5, 0]  -> medium similarity
#
#   Expected ranking: A > C > B
# ===========================================================================

unit_vec  = [1.0, 0.0, 0.0]
vec_A     = [0.9, 0.1, 0.0]
vec_B     = [0.0, 1.0, 0.0]
vec_C     = [0.5, 0.5, 0.0]

item_A = RawItem(source_type="YOUTUBE", title="A Video", url=None, raw_text="A raw")
item_B = RawItem(source_type="ARXIV",   title="B Paper", url=None, raw_text="B raw")
item_C = RawItem(source_type="NPTEL",   title="C Course", url=None, raw_text="C raw")

# score_items calls embed_texts([unit_context, A.raw_text, B.raw_text, C.raw_text])
# -> single API call returning 4 vectors
rank_client = _mock_client([_embed_resp(unit_vec, vec_A, vec_B, vec_C)])
with patch("app.modules.m05_learning_materials.embedder.get_embedder_client",
           return_value=rank_client):
    ranked = asyncio.run(
        score_items("unit context", [item_A, item_B, item_C],
                    tenant_schema="t", package_id="p")
    )

check("score_items returns 3 pairs",           len(ranked) == 3)
check("ranked[0] is item_A (highest sim)",     ranked[0][0] is item_A)
check("ranked[1] is item_C (medium sim)",      ranked[1][0] is item_C)
check("ranked[2] is item_B (zero sim)",        ranked[2][0] is item_B)
check("all scores in [0.0, 1.0]",
      all(0.0 <= s <= 1.0 for _, s in ranked))
check("scores in descending order",
      ranked[0][1] >= ranked[1][1] >= ranked[2][1])
check("item_B score is 0.0 (orthogonal)",      approx(ranked[2][1], 0.0))

# Verify score magnitudes
score_A = cosine_similarity(unit_vec, vec_A)
score_C = cosine_similarity(unit_vec, vec_C)
check("item_A score matches direct cosine",    approx(ranked[0][1], score_A))
check("item_C score matches direct cosine",    approx(ranked[1][1], score_C))

# ===========================================================================
# 8. score_items -- deterministic tie-breaking (title ascending)
# ===========================================================================

vec_tie = [0.7, 0.3, 0.0]  # same vector for both items -> identical scores

item_D = RawItem(source_type="YOUTUBE", title="AAA first",  url=None, raw_text="d raw")
item_E = RawItem(source_type="YOUTUBE", title="ZZZ second", url=None, raw_text="e raw")

tie_client = _mock_client([_embed_resp(unit_vec, vec_tie, vec_tie)])
with patch("app.modules.m05_learning_materials.embedder.get_embedder_client",
           return_value=tie_client):
    tied = asyncio.run(
        score_items("unit context", [item_E, item_D],  # E before D in input
                    tenant_schema="t", package_id="p")
    )

check("tie-break: D ('AAA') before E ('ZZZ') regardless of input order",
      tied[0][0] is item_D and tied[1][0] is item_E)
check("tied scores are equal",
      approx(tied[0][1], tied[1][1]))

# ===========================================================================
# 9. score_items -- EmbedderError propagates
# ===========================================================================

fail_c2 = _mock_client(Exception("embed fail"))
with patch("app.modules.m05_learning_materials.embedder.get_embedder_client",
           return_value=fail_c2):
    try:
        asyncio.run(
            score_items("ctx", [item_A], tenant_schema="t", package_id="p")
        )
        check("EmbedderError propagates through score_items", False)
    except EmbedderError:
        check("EmbedderError propagates through score_items", True)

# ===========================================================================
# 10. Module import: EmbedderError is an Exception subclass
# ===========================================================================
print("\n--- module contract ---")

check("EmbedderError is Exception subclass",  issubclass(EmbedderError, Exception))
check("get_embedder_client is callable",       callable(get_embedder_client))

# ===========================================================================
# Summary
# ===========================================================================
print(f"\n{'='*52}")
print(f"STEP-06 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL -- fix issues above before proceeding.")
    sys.exit(1)
else:
    print("ALL PASS -- STEP-06 smoke tests green.")
