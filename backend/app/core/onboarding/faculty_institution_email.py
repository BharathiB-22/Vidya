"""Faculty institution-email generation — Phase 1.5.

Faculty have no USN, so institution emails are derived from the faculty's name
(the student generator in ``institution_email_service`` stays untouched):

    {first_name_handle}@{institution_domain}   e.g.  kavya@lms.edu

Collisions are resolved with a numeric suffix (``kavya``, ``kavya2``, …) and
uniqueness is also enforced at the DB level by
``uq_faculty_profiles_institution_email``.  The generated address is stored for
the directory, communication and future SSO — it is NEVER the login identity
(login stays on ``users.email`` = the personal email).
"""
from __future__ import annotations

import re

from app.core.onboarding.institution_email_schemas import normalize_domain

# Honorifics / titles stripped before deriving the handle.
_TITLES = {"dr", "dr.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "miss"}


def faculty_local_part(full_name: str) -> str | None:
    """Derive a base local-part handle from a faculty full name.

    ``"Dr Kavya"`` → ``"kavya"``; ``"Dr. Arun Kumar"`` → ``"arun"``.
    Returns None when no usable alphanumeric token remains.
    """
    if not full_name:
        return None
    tokens = [t for t in re.split(r"\s+", full_name.strip()) if t]
    # Drop leading honorifics.
    while tokens and tokens[0].lower().strip(".") in {t.strip(".") for t in _TITLES}:
        tokens.pop(0)
    if not tokens:
        return None
    handle = re.sub(r"[^a-z0-9]", "", tokens[0].lower())
    return handle or None


def build_faculty_email(
    full_name: str,
    domain: str,
    taken: set[str],
) -> str | None:
    """Return a unique ``{handle}@{domain}`` not present in ``taken`` (lower-cased).

    Mutates ``taken`` by reserving the chosen address so repeated calls within a
    batch stay collision-free.  Returns None if no handle can be derived.
    """
    base = faculty_local_part(full_name)
    if not base:
        return None
    dom = normalize_domain(domain)
    candidate = f"{base}@{dom}"
    n = 1
    while candidate in taken:
        n += 1
        candidate = f"{base}{n}@{dom}"
    taken.add(candidate)
    return candidate
