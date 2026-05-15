"""
M05 Learning Material Packager — Source adapter base.

Provides:
  RawItem              provider-neutral material record
  SourceAdapterError   raised on exhausted retries or irrecoverable failures
  AbstractSourceAdapter Protocol with async search(query, limit) -> list[RawItem]
  HTTPX_TIMEOUT        shared httpx.Timeout(10.0)
  adapter_retry        tenacity decorator: 3 attempts, exp backoff 1s→30s
  get_adapter_logger   LoggerAdapter with tenant/provider context (R1, R6)

Isolation contract (R4):
  Adapters raise SourceAdapterError on exhaustion.
  The curation Celery task catches it per adapter, logs a warning, and continues.
  A package reaches READY even if 1–2 source adapters fail.
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any, Protocol, runtime_checkable

import httpx
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RawItem:
    """Provider-neutral material record returned by every source adapter."""
    source_type: str        # matches MaterialSourceType enum values
    title:       str
    url:         str | None
    raw_text:    str
    metadata:    dict[str, Any] = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class SourceAdapterError(Exception):
    """Raised after retries are exhausted or on an irrecoverable adapter failure.

    Caught per-adapter in the curation task so partial results are preserved.
    Never raised for transient errors — tenacity handles those via adapter_retry.
    """


# ---------------------------------------------------------------------------
# Shared httpx timeout
# ---------------------------------------------------------------------------

HTTPX_TIMEOUT = httpx.Timeout(10.0)


# ---------------------------------------------------------------------------
# Shared tenacity retry decorator
# ---------------------------------------------------------------------------

#: 3 attempts, exponential back-off 1s → 30s.
#: Does NOT retry SourceAdapterError (already a final failure signal).
adapter_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_not_exception_type(SourceAdapterError),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Structured logger helper (R6)
# ---------------------------------------------------------------------------

def get_adapter_logger(
    tenant_schema: str,
    source_provider: str,
) -> logging.LoggerAdapter:
    """Return a LoggerAdapter pre-loaded with R1/R6-compliant extra context."""
    return logging.LoggerAdapter(
        logging.getLogger("vidya.m05.adapters"),
        extra={
            "tenant_schema":   tenant_schema,
            "source_provider": source_provider,
        },
    )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class AbstractSourceAdapter(Protocol):
    async def search(self, query: str, limit: int) -> list[RawItem]: ...
