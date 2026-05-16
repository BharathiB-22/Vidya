"""
M06 Code Sandbox — subprocess-based code execution.

Interface: SandboxRunner.run(language, code, stdin, timeout_s) → SandboxResult
Clean interface allows swapping to Docker-based sandboxing in production.

Dev mode (Windows): subprocess.run() with timeout, no network, tmp dir.
Only Python is supported in dev; the interface is language-agnostic.

SandboxResult fields:
  stdout: captured stdout (truncated to M06_MAX_CODE_OUTPUT_CHARS)
  stderr: captured stderr (truncated)
  exit_code: int (None if timed out)
  timed_out: bool
  error: str | None (runner-level error, not execution error)
"""
from __future__ import annotations

import dataclasses
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger("vidya.m06.code_sandbox")


@dataclasses.dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Language dispatch
# ---------------------------------------------------------------------------

_SUPPORTED_LANGUAGES = {"python", "python3"}


def run(
    language: str,
    code: str,
    stdin: str = "",
    *,
    timeout_s: int | None = None,
) -> SandboxResult:
    """
    Execute `code` in a subprocess with a timeout.

    language: "python" | "python3"
    code: source code string
    stdin: standard input string
    timeout_s: seconds (defaults to settings.M06_CODE_TIMEOUT_SECONDS)

    Returns SandboxResult.
    """
    lang = (language or "python").lower().strip()
    timeout = timeout_s or settings.M06_CODE_TIMEOUT_SECONDS
    max_chars = settings.M06_MAX_CODE_OUTPUT_CHARS

    if lang not in _SUPPORTED_LANGUAGES:
        return SandboxResult(
            stdout="",
            stderr="",
            exit_code=None,
            timed_out=False,
            error=f"Language '{lang}' is not supported in dev sandbox. Supported: python.",
        )

    return _run_python(code, stdin, timeout_s=timeout, max_chars=max_chars)


# ---------------------------------------------------------------------------
# Python executor
# ---------------------------------------------------------------------------

def _run_python(
    code: str,
    stdin: str,
    *,
    timeout_s: int,
    max_chars: int,
) -> SandboxResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "submission.py"
        script_path.write_text(code, encoding="utf-8")

        python_exe = sys.executable  # use same Python as the worker

        try:
            proc = subprocess.run(
                [python_exe, str(script_path)],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=tmpdir,
                env={
                    **_minimal_env(),
                    "PYTHONPATH": "",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUTF8": "1",
                },
            )
            stdout = proc.stdout[:max_chars]
            stderr = proc.stderr[:max_chars]
            return SandboxResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode,
                timed_out=False,
            )

        except subprocess.TimeoutExpired:
            logger.warning("Code sandbox timed out after %ds", timeout_s)
            return SandboxResult(
                stdout="",
                stderr="",
                exit_code=None,
                timed_out=True,
                error=f"Execution timed out after {timeout_s} seconds.",
            )

        except Exception as exc:
            logger.exception("Code sandbox runner error: %s", exc)
            return SandboxResult(
                stdout="",
                stderr="",
                exit_code=None,
                timed_out=False,
                error=str(exc),
            )


def _minimal_env() -> dict[str, str]:
    """Minimal environment for subprocess — no sensitive vars."""
    keep = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "HOME", "USER", "LANG"}
    return {k: v for k, v in os.environ.items() if k in keep}
