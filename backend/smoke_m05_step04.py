"""STEP-04 smoke tests — M05 source adapter base."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import dataclasses
import logging

import httpx

from app.modules.m05_learning_materials.source_adapters.base import (
    AbstractSourceAdapter,
    HTTPX_TIMEOUT,
    RawItem,
    SourceAdapterError,
    adapter_retry,
    get_adapter_logger,
)
from app.modules.m05_learning_materials.source_adapters import (
    AbstractSourceAdapter as AbstractSourceAdapter2,
    RawItem as RawItem2,
)

# 1. RawItem is a dataclass with the required fields
fields = {f.name for f in dataclasses.fields(RawItem)}
assert fields == {"source_type", "title", "url", "raw_text", "metadata"}, \
    f"RawItem fields mismatch: {fields}"

# 2. RawItem instantiation with defaults
item = RawItem(source_type="YOUTUBE", title="Test", url="http://x", raw_text="hello")
assert item.metadata == {}, "metadata default should be empty dict"
assert item.source_type == "YOUTUBE"

# 3. RawItem metadata field is mutable per-instance (no shared default)
item_a = RawItem(source_type="ARXIV", title="A", url=None, raw_text="a")
item_b = RawItem(source_type="NPTEL", title="B", url=None, raw_text="b")
item_a.metadata["key"] = "val"
assert "key" not in item_b.metadata, "RawItem.metadata shares mutable default"

# 4. SourceAdapterError is an Exception subclass
assert issubclass(SourceAdapterError, Exception)
try:
    raise SourceAdapterError("boom")
except SourceAdapterError:
    pass

# 5. HTTPX_TIMEOUT is an httpx.Timeout with 10s
assert isinstance(HTTPX_TIMEOUT, httpx.Timeout)
assert HTTPX_TIMEOUT.connect == 10.0
assert HTTPX_TIMEOUT.read == 10.0

# 6. adapter_retry is callable (tenacity decorator)
assert callable(adapter_retry)

# 7. adapter_retry does NOT retry SourceAdapterError
import asyncio

call_count = 0

@adapter_retry
async def _raises_adapter_error():
    global call_count
    call_count += 1
    raise SourceAdapterError("final")

try:
    asyncio.get_event_loop().run_until_complete(_raises_adapter_error())
except SourceAdapterError:
    pass
assert call_count == 1, \
    f"adapter_retry should not retry SourceAdapterError (called {call_count} times)"

# 8. adapter_retry retries transient exceptions (up to 3 attempts)
transient_count = 0

@adapter_retry
async def _raises_transient():
    global transient_count
    transient_count += 1
    raise ValueError("transient")

try:
    asyncio.get_event_loop().run_until_complete(_raises_transient())
except ValueError:
    pass
assert transient_count == 3, \
    f"adapter_retry should attempt 3 times on transient errors (got {transient_count})"

# 9. get_adapter_logger returns a LoggerAdapter with correct extra keys
logger = get_adapter_logger("tenant_abc", "YOUTUBE")
assert isinstance(logger, logging.LoggerAdapter)
assert logger.extra["tenant_schema"] == "tenant_abc"
assert logger.extra["source_provider"] == "YOUTUBE"

# 10. Package __init__ re-exports same objects
assert AbstractSourceAdapter2 is AbstractSourceAdapter
assert RawItem2 is RawItem

# 11. AbstractSourceAdapter is runtime_checkable Protocol
from typing import runtime_checkable, Protocol
assert issubclass(AbstractSourceAdapter, Protocol)

print("STEP-04: all 11 assertions passed.")
