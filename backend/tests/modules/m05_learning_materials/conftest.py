"""
Test configuration for M05 learning materials tests.

Installs a qdrant_client stub into sys.modules so the worker and RAG service
can be imported and tested without the real qdrant-client package installed.
The actual Qdrant client is replaced by an AsyncMock in every test.
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock


def _install_qdrant_stub() -> None:
    if "qdrant_client" in sys.modules:
        return

    # --- indexing models (STEP-09) ---

    class PointStruct:
        def __init__(self, *, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    class Distance:
        COSINE = "Cosine"
        DOT = "Dot"
        EUCLID = "Euclid"

    class VectorParams:
        def __init__(self, *, size, distance):
            self.size = size
            self.distance = distance

    # --- search / filter models (STEP-10) ---

    class MatchValue:
        def __init__(self, *, value):
            self.value = value

    class MatchAny:
        def __init__(self, *, any):
            self.any = any

    class FieldCondition:
        def __init__(self, *, key, match=None, range=None):
            self.key = key
            self.match = match
            self.range = range

    class Filter:
        def __init__(self, *, must=None, should=None, must_not=None):
            self.must = must or []
            self.should = should or []
            self.must_not = must_not or []

    # --- exception stubs ---

    class UnexpectedResponse(Exception):
        pass

    models_mod = ModuleType("qdrant_client.models")
    models_mod.PointStruct = PointStruct
    models_mod.Distance = Distance
    models_mod.VectorParams = VectorParams
    models_mod.MatchValue = MatchValue
    models_mod.MatchAny = MatchAny
    models_mod.FieldCondition = FieldCondition
    models_mod.Filter = Filter

    http_mod = ModuleType("qdrant_client.http")
    exceptions_mod = ModuleType("qdrant_client.http.exceptions")
    exceptions_mod.UnexpectedResponse = UnexpectedResponse

    root_mod = ModuleType("qdrant_client")
    root_mod.AsyncQdrantClient = MagicMock
    root_mod.models = models_mod

    sys.modules["qdrant_client"] = root_mod
    sys.modules["qdrant_client.models"] = models_mod
    sys.modules["qdrant_client.http"] = http_mod
    sys.modules["qdrant_client.http.exceptions"] = exceptions_mod


_install_qdrant_stub()
