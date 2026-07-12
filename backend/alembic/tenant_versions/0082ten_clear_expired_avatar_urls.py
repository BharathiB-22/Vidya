"""tenant: null out expired presigned avatar URLs

Revision ID: 0082ten
Revises: 0081ten
Create Date: 2026-07-10

Until now `users.avatar_url` held the *presigned GET URL* handed back by the
storage module right after upload. Those URLs carry an expiry (see
PRESIGNED_URL_EXPIRY_MINUTES_GET), so every stored value went stale within
hours: the browser then requested an object it was no longer authorised for and
the profile picture rendered as a broken image (or as a 403 from MinIO/S3).

Avatars are now persisted as the storage *object key*
(`vidya-assets/{tenant_slug}/avatar/{user_id}/{uuid}-photo.{ext}`) and signed
fresh on every read, so the value in this column no longer expires.

This migration drops the leftovers. Anything that is not an object key can only
be one of those dead presigned URLs — `users.avatar_url` has never had another
writer than the avatar upload flow (added in 0074ten). Affected users fall back
to their initials, exactly as a user who never uploaded a picture does, and can
re-upload to get it back. No image is deleted; only the dangling reference is.

`platform_users.avatar_url` (public schema) is deliberately left alone: that
column was populated by a paste-your-own-URL field, so its non-key values are
real external URLs that still resolve.

Irreversible by nature — an expired URL cannot be un-expired, and the row it
came from carries no way to recover the object key.
"""

from alembic import op

revision      = "0082ten"
down_revision = "0081ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # starts_with() rather than LIKE 'vidya-assets/%': op.execute hands the
    # statement to psycopg2 with a (empty) parameter map, so a bare `%` would be
    # read as an interpolation placeholder and blow up.
    op.execute(
        """
        UPDATE users
           SET avatar_url = NULL
         WHERE avatar_url IS NOT NULL
           AND NOT starts_with(avatar_url, 'vidya-assets/')
        """
    )


def downgrade() -> None:
    # Nothing to restore: the previous values were URLs that had already expired.
    pass
