"""
M04 Coursework AI — multi-provider chain with typed failure classification.

Priority: Gemini -> Groq -> DeepSeek. Each provider is tried in order; a provider
is SKIPPED if its key is absent. Failures are classified so the caller can decide
retry semantics:

  ProviderConfigError    -> skip this provider, try the next (missing/invalid key,
                            401/403/404, unsupported model).
  ProviderTransientError -> try the next provider (timeout, 429, 5xx, network,
                            quota, provider unavailable).
  ProviderPermanentError -> stop the whole chain (400 malformed prompt) — the same
                            prompt would fail everywhere, so no fallback/retry.

run_chain() raises:
  TransientAIError  when every configured provider failed transiently
                    -> the worker lets Celery autoretry the task.
  PermanentAIError  when no provider is usable, or a permanent error occurred
                    -> the worker records status=FAILED (no retry).

Only orchestration lives here — no prompt building, no parsing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger("vidya.m04.ai_providers")


# --- Exceptions -------------------------------------------------------------

class ProviderConfigError(Exception):
    """This provider can't be used (bad/missing key, 401/403/404). Skip it."""


class ProviderTransientError(Exception):
    """Temporary provider failure (timeout, 429, 5xx, network). Try the next."""


class ProviderPermanentError(Exception):
    """The request itself is bad (400). No fallback would help."""


class TransientAIError(Exception):
    """Every configured provider failed transiently — safe to retry later."""


class PermanentAIError(Exception):
    """No usable provider, or a permanent failure. Do not retry."""


@dataclass
class ChainResult:
    raw: str
    provider_used: str
    model_used: str
    fallback_chain: str   # e.g. "gemini→groq"


# --- Error classification ---------------------------------------------------

def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code", "http_status"):
        v = getattr(exc, attr, None)
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def _classify(exc: Exception) -> str:
    """Return 'config' | 'transient' | 'permanent' from any provider SDK error."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    code = _status_code(exc)

    # Config: skip provider entirely.
    if code in (401, 403, 404):
        return "config"
    if any(s in name for s in ("authentication", "permission")) or any(
        s in msg for s in ("api key", "unauthorized", "invalid key", "invalid_api_key",
                            "unsupported model", "model_not_found", "not found")
    ):
        return "config"

    # Permanent: a 400 bad request — the prompt/request is malformed.
    if code == 400 or "bad request" in msg or "invalid_request_error" in msg:
        return "permanent"

    # Transient: retryable.
    if code == 429 or (code is not None and 500 <= code < 600):
        return "transient"
    if any(s in name for s in ("timeout", "connection", "unavailable", "serviceunavailable")):
        return "transient"
    if any(s in msg for s in (
        "timeout", "timed out", "429", "rate limit", "rate_limit", "quota",
        "resource_exhausted", "unavailable", "overloaded", "temporarily",
        "connection", "502", "503", "504",
    )):
        return "transient"

    # Unknown → treat as transient so we fall back / retry rather than hard-fail.
    return "transient"


def _raise_classified(provider: str, exc: Exception):
    kind = _classify(exc)
    text = f"{provider}: {type(exc).__name__}: {exc!s:.200}"
    if kind == "config":
        raise ProviderConfigError(text) from exc
    if kind == "permanent":
        raise ProviderPermanentError(text) from exc
    raise ProviderTransientError(text) from exc


# --- Providers --------------------------------------------------------------

async def _gemini(system: str, user: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
        system_instruction=system,
    )
    try:
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL, contents=user, config=config,
        )
    except Exception as exc:  # noqa: BLE001 — classified below
        _raise_classified("gemini", exc)
    raw = getattr(response, "text", "") or ""
    if not raw.strip():
        raise ProviderTransientError("gemini: empty response")
    return raw


async def _openai_compatible(provider: str, base_url: str, api_key: str, model: str,
                             system: str, user: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001 — classified below
        _raise_classified(provider, exc)
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ProviderTransientError(f"{provider}: empty response")
    return raw


async def _groq(system: str, user: str) -> str:
    return await _openai_compatible(
        "groq", "https://api.groq.com/openai/v1",
        settings.GROQ_API_KEY, settings.GROQ_MODEL, system, user,
    )


async def _deepseek(system: str, user: str) -> str:
    return await _openai_compatible(
        "deepseek", "https://api.deepseek.com",
        settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_MODEL, system, user,
    )


# --- Chain ------------------------------------------------------------------

def _configured_providers() -> list[tuple[str, str, object]]:
    """Ordered [(name, model, coroutine_fn)] for providers that have a key.
    A missing key means the provider is skipped automatically."""
    chain: list[tuple[str, str, object]] = []
    if settings.GEMINI_API_KEY:
        chain.append(("gemini", settings.GEMINI_MODEL, _gemini))
    if settings.GROQ_API_KEY:
        chain.append(("groq", settings.GROQ_MODEL, _groq))
    if settings.DEEPSEEK_API_KEY and getattr(settings, "AI_DEEPSEEK_ENABLED", True):
        chain.append(("deepseek", settings.DEEPSEEK_MODEL, _deepseek))
    return chain


async def run_chain(system: str, user: str) -> ChainResult:
    """Try providers in priority order. Falls back on config/transient failures;
    stops on a permanent (400) failure. See module docstring for the contract."""
    providers = _configured_providers()
    if not providers:
        raise PermanentAIError("No AI provider configured (no API keys present).")

    attempted: list[str] = []
    transient_seen = False
    last_err: Exception | None = None

    for name, model, fn in providers:
        attempted.append(name)
        try:
            raw = await fn(system, user)
            return ChainResult(
                raw=raw, provider_used=name, model_used=model,
                fallback_chain="→".join(attempted),
            )
        except ProviderPermanentError as exc:
            # Same prompt would fail on every provider — stop now.
            raise PermanentAIError(str(exc)) from exc
        except ProviderConfigError as exc:
            logger.warning("coursework AI: skipping %s (config): %s", name, exc)
            last_err = exc
            continue
        except ProviderTransientError as exc:
            logger.warning("coursework AI: %s transient failure: %s", name, exc)
            transient_seen = True
            last_err = exc
            continue

    if transient_seen:
        raise TransientAIError(
            f"All AI providers failed transiently (chain: {'→'.join(attempted)}). "
            f"Last: {last_err}"
        )
    # Everything was a config skip → nothing usable; retrying won't help.
    raise PermanentAIError(
        f"No usable AI provider (chain: {'→'.join(attempted)}). Last: {last_err}"
    )
