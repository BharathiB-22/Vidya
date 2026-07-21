import inspect
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from jose import JWTError

from app.core.auth.security import (
    create_access_token,
    create_reset_token,
    decode_token,
    generate_otp,
    generate_refresh_token,
    hash_otp,
    hash_password,
    hash_token,
    verify_otp,
    verify_password,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_hash_password_verify_correct():
    hashed = hash_password("secret")
    assert isinstance(hashed, str)
    assert len(hashed) > 0
    assert verify_password("secret", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("secret")
    assert verify_password("wrong", hashed) is False


def test_hash_password_different_salts():
    hash1 = hash_password("same")
    hash2 = hash_password("same")
    assert hash1 != hash2
    assert verify_password("same", hash1) is True
    assert verify_password("same", hash2) is True


# ---------------------------------------------------------------------------
# JWT access token
# ---------------------------------------------------------------------------


def test_create_and_decode_access_token():
    uid = str(uuid4())
    token = create_access_token({"sub": uid, "role": "FACULTY"})
    decoded = decode_token(token)
    assert "sub" in decoded
    assert "role" in decoded
    assert "iat" in decoded
    assert "exp" in decoded
    assert decoded["exp"] > decoded["iat"]


def test_access_token_expiry_claim():
    token = create_access_token({}, expires_delta=timedelta(minutes=30))
    decoded = decode_token(token)
    diff = decoded["exp"] - decoded["iat"]
    assert abs(diff - 1800) <= 5


def test_expired_access_token_raises():
    token = create_access_token({}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(JWTError):
        decode_token(token)


def test_tampered_token_raises():
    token = create_access_token({"sub": str(uuid4())})
    if token.endswith("a"):
        tampered = token[:-1] + "b"
    else:
        tampered = token[:-1] + "a"
    with pytest.raises(JWTError):
        decode_token(tampered)


# ---------------------------------------------------------------------------
# Reset token
# ---------------------------------------------------------------------------


def test_create_and_decode_reset_token():
    uid = uuid4()
    token = create_reset_token(uid, "tenant_abc", datetime.now(timezone.utc))
    decoded = decode_token(token)
    assert decoded["sub"] == str(uid)
    assert decoded["purpose"] == "PASSWORD_RESET"
    assert decoded["schema_name"] == "tenant_abc"
    assert "iat_cutoff" in decoded


def test_reset_token_null_schema():
    token = create_reset_token(uuid4(), None, datetime.now(timezone.utc))
    decoded = decode_token(token)
    assert decoded["schema_name"] is None


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------


def test_generate_refresh_token_non_empty():
    token = generate_refresh_token()
    assert isinstance(token, str)
    assert len(token) >= 32


def test_generate_refresh_token_unique():
    tokens = [generate_refresh_token() for _ in range(10)]
    assert len(set(tokens)) == 10


# ---------------------------------------------------------------------------
# Token hashing
# ---------------------------------------------------------------------------


def test_hash_token_deterministic():
    assert hash_token("abc") == hash_token("abc")


def test_hash_token_different_inputs():
    assert hash_token("abc") != hash_token("xyz")


# ---------------------------------------------------------------------------
# OTP generation
# ---------------------------------------------------------------------------


def test_generate_otp_format():
    otp = generate_otp()
    assert len(otp) == 6
    assert otp.isdigit() is True


def test_generate_otp_zero_padded():
    otps = [generate_otp() for _ in range(200)]
    for otp in otps:
        assert len(otp) == 6


def test_generate_otp_unique():
    otps = [generate_otp() for _ in range(50)]
    assert len(set(otps)) >= 40


# ---------------------------------------------------------------------------
# OTP verification
# ---------------------------------------------------------------------------


def test_hash_otp_and_verify_correct():
    assert verify_otp("042137", hash_otp("042137")) is True


def test_verify_otp_wrong():
    assert verify_otp("000000", hash_otp("042137")) is False


def test_verify_otp_uses_compare_digest():
    source = inspect.getsource(verify_otp)
    assert "compare_digest" in source
