"""Profile picture upload — content-type negotiation and object-key resolution.

Regression guard for the "Input should be a valid UUID" upload failure: avatars
are now uploaded as multipart with the owner taken from the token, and the
tenant DB stores an object key rather than an expiring signed URL.
"""
import pytest

from app.core.storage.avatar import (
    PLATFORM_SCOPE_SLUG,
    normalize_avatar_upload,
    resolve_avatar_url,
)
from app.core.storage.repository import StorageRepository
from app.core.storage.service import StorageService

_OWNER = "11111111-1111-1111-1111-111111111111"
_KEY = f"vidya-assets/acme/avatar/{_OWNER}/22222222-2222-2222-2222-222222222222-photo.png"


class TestNormalizeAvatarUpload:
    @pytest.mark.parametrize(
        "filename,content_type,expected_type,expected_ext",
        [
            ("me.jpg", "image/jpeg", "image/jpeg", ".jpg"),
            ("me.jpeg", "image/jpeg", "image/jpeg", ".jpeg"),
            ("me.png", "image/png", "image/png", ".png"),
            ("me.webp", "image/webp", "image/webp", ".webp"),
            # Browsers that report a non-canonical JPEG type.
            ("me.jpg", "image/jpg", "image/jpeg", ".jpg"),
            ("me.jpg", "image/pjpeg", "image/jpeg", ".jpg"),
            # Content type carries a charset parameter.
            ("me.png", "image/png; charset=binary", "image/png", ".png"),
            # Unhelpful content type — extension decides.
            ("PHOTO.WEBP", "application/octet-stream", "image/webp", ".webp"),
            ("me.png", None, "image/png", ".png"),
        ],
    )
    def test_accepts_all_four_formats(self, filename, content_type, expected_type, expected_ext):
        assert normalize_avatar_upload(filename, content_type) == (expected_type, expected_ext)

    @pytest.mark.parametrize(
        "filename,content_type",
        [
            ("virus.exe", "application/octet-stream"),
            ("doc.pdf", "application/pdf"),
            ("anim.gif", "image/gif"),
            ("logo.svg", "image/svg+xml"),
            (None, None),
            ("noextension", ""),
        ],
    )
    def test_rejects_everything_else(self, filename, content_type):
        with pytest.raises(ValueError):
            normalize_avatar_upload(filename, content_type)


class TestResolveAvatarUrl:
    def test_missing_avatar_stays_missing(self):
        """Users who never uploaded a picture keep working."""
        assert resolve_avatar_url(None) is None
        assert resolve_avatar_url("") is None
        assert resolve_avatar_url("   ") is None

    def test_object_key_is_signed(self):
        url = resolve_avatar_url(_KEY)
        assert url is not None
        assert url.startswith("http")
        assert "avatar" in url
        assert "X-Amz-Signature" in url or "Signature" in url

    def test_legacy_full_url_passes_through(self):
        assert resolve_avatar_url("https://cdn.example.com/a.png") == "https://cdn.example.com/a.png"
        assert resolve_avatar_url("/static/a.png") == "/static/a.png"

    def test_unrenderable_junk_becomes_none(self):
        """Never hand the UI a string it would render as a broken image."""
        assert resolve_avatar_url("not-a-url") is None
        assert resolve_avatar_url(_OWNER) is None


class TestAvatarObjectKey:
    def _key(self, scope: str) -> str:
        return StorageService._generate_object_key(
            tenant_slug=scope,
            entity_type="avatar",
            entity_id=_OWNER,
            original_filename="photo.webp",
        )

    def test_tenant_key_is_scoped_and_valid(self):
        key = self._key("acme")
        assert key.startswith(f"vidya-assets/acme/avatar/{_OWNER}/")
        assert key.endswith("-photo.webp")
        assert StorageRepository._validate_object_key(key)

    def test_platform_scope_is_valid(self):
        """Super admins belong to no tenant, so they get the platform prefix."""
        key = self._key(PLATFORM_SCOPE_SLUG)
        assert key.startswith(f"vidya-assets/{PLATFORM_SCOPE_SLUG}/avatar/")
        assert StorageRepository._validate_object_key(key)


class TestUploadValidation:
    @pytest.mark.asyncio
    async def test_empty_file_rejected(self):
        from app.core.storage.service import StorageError

        with pytest.raises(StorageError) as e:
            await StorageService.upload_avatar(
                owner_id=_OWNER, scope_slug="acme",
                filename="a.png", content_type="image/png", data=b"",
            )
        assert e.value.code == "EMPTY_FILE"

    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self):
        from app.config import settings
        from app.core.storage.service import StorageError

        too_big = b"x" * (settings.AVATAR_MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1)
        with pytest.raises(StorageError) as e:
            await StorageService.upload_avatar(
                owner_id=_OWNER, scope_slug="acme",
                filename="a.png", content_type="image/png", data=too_big,
            )
        assert e.value.code == "FILE_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_wrong_format_rejected_before_touching_storage(self):
        from app.core.storage.service import StorageError

        with pytest.raises(StorageError) as e:
            await StorageService.upload_avatar(
                owner_id=_OWNER, scope_slug="acme",
                filename="a.gif", content_type="image/gif", data=b"GIF89a",
            )
        assert e.value.code == "INVALID_CONTENT_TYPE"
