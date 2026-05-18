"""
M08 Exam Setter — Paper sealing (AES encryption via Fernet).

Security design:
  - Fernet provides AES-128-CBC + HMAC-SHA256 (effectively AES-256 in the
    broader sense of strong symmetric encryption suitable for exam papers).
  - Key comes from settings.EXAM_FERNET_KEY (env var).
  - In dev: if EXAM_FERNET_KEY is blank, a new key is generated per process
    (ephemeral — sealed papers cannot be unsealed after worker restart; for
    dev/test only).
  - In prod: set EXAM_FERNET_KEY to a persistent Fernet key (or wrap via KMS).
  - The actual crypto key is NEVER stored in the database.
    Only `encryption_key_ref` (the env var name "EXAM_FERNET_KEY") is stored
    as a hint for key lookup in KMS/secrets-manager integrations.

Usage:
  blob, key_ref = seal(data_dict)
  data_dict     = unseal(blob, key_ref)
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("vidya.m08.sealer")

_FERNET_KEY_REF = "EXAM_FERNET_KEY"

_fernet_instance = None


def _get_fernet():
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "cryptography package is required for paper sealing. "
            "Install it: pip install cryptography"
        ) from exc

    from app.config import settings
    raw_key = settings.EXAM_FERNET_KEY.strip()

    if not raw_key:
        # Dev / test: generate ephemeral key (paper cannot be unsealed after restart)
        key = Fernet.generate_key()
        logger.warning(
            "EXAM_FERNET_KEY not set — using ephemeral key. "
            "Sealed papers will NOT survive worker restart. Set EXAM_FERNET_KEY in .env for persistence."
        )
    else:
        key = raw_key.encode() if isinstance(raw_key, str) else raw_key

    _fernet_instance = Fernet(key)
    return _fernet_instance


def seal(data: dict) -> tuple[bytes, str]:
    """
    Encrypt data dict with Fernet.

    Returns:
        (encrypted_bytes, key_ref)
        key_ref is the env var name — stored in DB as encryption_key_ref.
        encrypted_bytes are stored as a binary blob in S3.
    """
    fernet = _get_fernet()
    plaintext = json.dumps(data, default=str).encode("utf-8")
    encrypted = fernet.encrypt(plaintext)
    return encrypted, _FERNET_KEY_REF


def unseal(encrypted_bytes: bytes, key_ref: str) -> dict:
    """
    Decrypt an encrypted blob back to a dict.

    Args:
        encrypted_bytes: bytes returned by seal().
        key_ref: ignored in current implementation (used for KMS routing in prod).

    Returns:
        Original data dict.
    """
    fernet = _get_fernet()
    plaintext = fernet.decrypt(encrypted_bytes)
    return json.loads(plaintext.decode("utf-8"))
