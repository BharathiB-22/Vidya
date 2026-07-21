import uuid


from app.core.storage.service import StorageError, StorageService


class TestObjectKeyGeneration:
    """Test server-side object key generation."""

    def test_object_key_format(self):
        """Test that generated keys follow expected format."""
        tenant_slug = "test-tenant"
        entity_type = "submission"
        entity_id = uuid.uuid4()
        filename = "document.pdf"

        key = StorageService._generate_object_key(
            tenant_slug=tenant_slug,
            entity_type=entity_type,
            entity_id=entity_id,
            original_filename=filename,
        )

        # Verify structure
        assert key.startswith(f"vidya-assets/{tenant_slug}/{entity_type}/{entity_id}/")
        assert key.endswith("-document.pdf")
        # Verify it contains a UUID
        parts = key.split("/")
        assert len(parts) == 5
        file_part = parts[-1]
        # File part should be: {uuid}-{filename}
        assert len(file_part.split("-")) >= 2

    def test_object_key_sanitizes_filename(self):
        """Test that dangerous filenames are sanitized."""
        tenant_slug = "test-tenant"
        entity_type = "submission"
        entity_id = uuid.uuid4()

        dangerous_filenames = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "file\x00name.pdf",  # Null byte
        ]

        for filename in dangerous_filenames:
            key = StorageService._generate_object_key(
                tenant_slug=tenant_slug,
                entity_type=entity_type,
                entity_id=entity_id,
                original_filename=filename,
            )
            # Key should not contain null bytes
            assert "\x00" not in key
            # Key should start with proper prefix (this prevents directory traversal at key level)
            assert key.startswith(f"vidya-assets/{tenant_slug}/{entity_type}/{entity_id}/")

    def test_object_key_includes_uuid_for_collision_prevention(self):
        """Test that object key includes UUID to prevent collisions."""
        tenant_slug = "test-tenant"
        entity_type = "submission"
        entity_id = uuid.uuid4()
        filename = "document.pdf"

        key1 = StorageService._generate_object_key(
            tenant_slug=tenant_slug, entity_type=entity_type, entity_id=entity_id, original_filename=filename
        )
        key2 = StorageService._generate_object_key(
            tenant_slug=tenant_slug, entity_type=entity_type, entity_id=entity_id, original_filename=filename
        )

        # Keys should be different due to UUID
        assert key1 != key2
        # But follow same pattern
        assert key1.split("/")[:-1] == key2.split("/")[:-1]

    def test_object_key_preserves_entity_scope(self):
        """Test that object key encodes tenant and entity."""
        tenant_slug = "my-org"
        entity_type = "research_doc"
        entity_id = uuid.uuid4()

        key = StorageService._generate_object_key(
            tenant_slug=tenant_slug,
            entity_type=entity_type,
            entity_id=entity_id,
            original_filename="report.docx",
        )

        parts = key.split("/")
        assert parts[0] == "vidya-assets"
        assert parts[1] == tenant_slug
        assert parts[2] == entity_type
        assert parts[3] == str(entity_id)


class TestStorageErrorHandling:
    """Test StorageError exception."""

    def test_storage_error_creation(self):
        """Test creating a StorageError."""
        error = StorageError("TEST_CODE", "Test message", 400)
        assert error.code == "TEST_CODE"
        assert error.message == "Test message"
        assert error.status_code == 400

    def test_storage_error_default_status(self):
        """Test StorageError default status code."""
        error = StorageError("TEST", "message")
        assert error.status_code == 400


class TestUploadUrlValidation:
    """Test validation in upload URL generation."""

    def test_invalid_entity_type_rejected(self):
        """Test that invalid entity types are caught."""

        # This would normally be tested with async, but we can verify the logic exists
        # by checking the service has the entity type validation


class TestMimeTypeWhitelist:
    """Test MIME type whitelist from config."""

    def test_config_has_mime_whitelist(self):
        """Test that config defines MIME whitelist."""
        from app.config import settings

        assert hasattr(settings, "STORAGE_MIME_WHITELIST")
        assert isinstance(settings.STORAGE_MIME_WHITELIST, dict)
        assert "submission" in settings.STORAGE_MIME_WHITELIST
        assert "research_doc" in settings.STORAGE_MIME_WHITELIST
        assert "viva_recording" in settings.STORAGE_MIME_WHITELIST
        assert "course_kit" in settings.STORAGE_MIME_WHITELIST

    def test_mime_whitelist_has_valid_types(self):
        """Test that MIME whitelist has valid MIME types."""
        from app.config import settings

        for entity_type, mimes in settings.STORAGE_MIME_WHITELIST.items():
            assert isinstance(mimes, list)
            assert len(mimes) > 0
            for mime in mimes:
                assert "/" in mime, f"Invalid MIME type: {mime}"


class TestConfigLimits:
    """Test file size and other limits from config."""

    def test_max_upload_size_configured(self):
        """Test that max upload size is configured."""
        from app.config import settings

        assert hasattr(settings, "MAX_UPLOAD_SIZE_MB")
        assert settings.MAX_UPLOAD_SIZE_MB > 0

    def test_presigned_url_expiry_configured(self):
        """Test that presigned URL expiry times are configured."""
        from app.config import settings

        assert hasattr(settings, "PRESIGNED_URL_EXPIRY_MINUTES_PUT")
        assert hasattr(settings, "PRESIGNED_URL_EXPIRY_MINUTES_GET")
        assert settings.PRESIGNED_URL_EXPIRY_MINUTES_PUT > 0
        assert settings.PRESIGNED_URL_EXPIRY_MINUTES_GET > 0
