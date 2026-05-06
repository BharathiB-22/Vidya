import re

import pytest

from app.core.tenants.provisioner import derive_schema_name, generate_slug

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
