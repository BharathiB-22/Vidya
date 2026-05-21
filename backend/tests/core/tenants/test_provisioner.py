import re

import pytest

from app.core.tenants.provisioner import derive_schema_name, generate_slug
from app.core.tenants.schemas import CreateTenantRequest, _validate_password_complexity

_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]+$")


# ---------------------------------------------------------------------------
# generate_slug
# ---------------------------------------------------------------------------


def test_generate_slug_basic():
    assert generate_slug("MIT University") == "mit-university"


def test_generate_slug_unicode():
    # é normalises to e + combining accent; ascii encode drops the combining char
    assert generate_slug("Université de Paris") == "universite-de-paris"


def test_generate_slug_special_chars():
    # dots and exclamation become hyphens; consecutive non-alphanum collapses
    assert generate_slug("I.I.T. Bombay!") == "i-i-t-bombay"


def test_generate_slug_numbers():
    assert generate_slug("University 21") == "university-21"


def test_generate_slug_truncate_length():
    long_name = "x" * 60
    slug = generate_slug(long_name)
    assert len(slug) <= 50


def test_generate_slug_no_trailing_hyphen_after_truncate():
    # Build a name whose slug is longer than 50 chars so truncation occurs.
    # "anna university chennai" repeated gives a slug with interior hyphens.
    name = "Anna University Chennai India Extended Name For Test"
    slug = generate_slug(name)
    assert len(slug) <= 50
    assert not slug.endswith("-")
    assert not slug.startswith("-")


def test_generate_slug_empty_raises():
    # All characters are stripped → empty slug → ValueError
    with pytest.raises(ValueError, match="empty slug"):
        generate_slug("---!!!")


def test_generate_slug_whitespace_only_raises():
    with pytest.raises(ValueError, match="empty slug"):
        generate_slug("   ")


def test_generate_slug_strips_leading_trailing_hyphens():
    slug = generate_slug("  !!Hello World!!  ")
    assert not slug.startswith("-")
    assert not slug.endswith("-")
    assert "hello" in slug


# ---------------------------------------------------------------------------
# derive_schema_name
# ---------------------------------------------------------------------------


def test_derive_schema_name_basic():
    assert derive_schema_name("iit-bombay") == "tenant_iit_bombay"


def test_derive_schema_name_single_word():
    assert derive_schema_name("mit") == "tenant_mit"


def test_derive_schema_name_multiple_hyphens():
    assert derive_schema_name("a-b-c-d") == "tenant_a_b_c_d"


def test_derive_schema_name_satisfies_regex():
    for slug in ["iit-bombay", "mit", "university-21", "abc"]:
        schema = derive_schema_name(slug)
        assert _SCHEMA_RE.match(schema), f"{schema!r} did not match schema regex"


def test_slug_to_schema_roundtrip():
    slug = generate_slug("IIT Bombay")
    schema = derive_schema_name(slug)
    assert _SCHEMA_RE.match(schema)


# ---------------------------------------------------------------------------
# password complexity (_validate_password_complexity)
# ---------------------------------------------------------------------------


def test_password_complexity_valid():
    # Should not raise for a fully compliant password
    result = _validate_password_complexity("Admin1234!")
    assert result == "Admin1234!"


def test_password_complexity_valid_various():
    for pw in ["Secure#99", "P@ssw0rd", "Abc!1234", "Complex$1X"]:
        assert _validate_password_complexity(pw) == pw


def test_password_complexity_too_short():
    with pytest.raises(ValueError, match="8 characters"):
        _validate_password_complexity("Ab1!")


def test_password_complexity_no_uppercase():
    with pytest.raises(ValueError, match="uppercase"):
        _validate_password_complexity("admin1234!")


def test_password_complexity_no_lowercase():
    with pytest.raises(ValueError, match="lowercase"):
        _validate_password_complexity("ADMIN1234!")


def test_password_complexity_no_digit():
    with pytest.raises(ValueError, match="digit"):
        _validate_password_complexity("Admin!!!!!")


def test_password_complexity_no_special():
    with pytest.raises(ValueError, match="special"):
        _validate_password_complexity("Admin1234")


def test_password_complexity_multiple_failures():
    # All-lowercase, no digit, no special → error mentions multiple issues
    with pytest.raises(ValueError, match="uppercase"):
        _validate_password_complexity("alllower")


# ---------------------------------------------------------------------------
# CreateTenantRequest password validator integration
# ---------------------------------------------------------------------------


def test_create_request_rejects_weak_password():
    with pytest.raises(Exception):  # pydantic ValidationError
        CreateTenantRequest(
            name="Test University",
            admin_email="admin@test.edu",
            admin_password="weakpass",  # no upper, digit, special
            admin_full_name="Admin",
        )


def test_create_request_accepts_strong_password():
    req = CreateTenantRequest(
        name="Test University",
        admin_email="admin@test.edu",
        admin_password="Admin1234!",
        admin_full_name="Admin",
    )
    assert req.admin_password == "Admin1234!"


def test_create_request_contact_email_defaults_none():
    req = CreateTenantRequest(
        name="Test University",
        admin_email="admin@test.edu",
        admin_password="Admin1234!",
        admin_full_name="Admin",
    )
    assert req.contact_email is None


def test_create_request_contact_email_set():
    req = CreateTenantRequest(
        name="Test University",
        admin_email="admin@test.edu",
        admin_password="Admin1234!",
        admin_full_name="Admin",
        contact_email="contact@test.edu",
    )
    assert str(req.contact_email) == "contact@test.edu"
