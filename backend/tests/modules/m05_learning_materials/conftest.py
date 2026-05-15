"""
Test configuration for M05 learning materials tests.

Installs a qdrant_client stub into sys.modules so the worker can be
imported and tested without the real qdrant-client package installed.
The actual Qdrant client is replaced by an AsyncMock in every test.
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock


def _install_qdrant_stub() -> None:
    if "qdrant_client" in sys.modules:
        return

    # Minimal PointStruct that the worker builds and the tests inspect.
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

    models_mod = ModuleType("qdrant_client.models")
    models_mod.PointStruct = PointStruct
    models_mod.Distance = Distance
    models_mod.VectorParams = VectorParams

    http_mod = ModuleType("qdrant_client.http")
    exceptions_mod = ModuleType("qdrant_client.http.exceptions")

    class UnexpectedResponse(Exception):
        pass

    exceptions_mod.UnexpectedResponse = UnexpectedResponse

    root_mod = ModuleType("qdrant_client")
    root_mod.AsyncQdrantClient = MagicMock
    root_mod.models = models_mod

    sys.modules["qdrant_client"] = root_mod
    sys.modules["qdrant_client.models"] = models_mod
    sys.modules["qdrant_client.http"] = http_mod
    sys.modules["qdrant_client.http.exceptions"] = exceptions_mod


_install_qdrant_stub()
