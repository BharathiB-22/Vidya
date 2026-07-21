import uuid


from app.core.storage.repository import StorageRepository


class TestObjectKeyValidation:
    """Test object key format validation (no database needed)."""

    def test_valid_object_keys(self):
        """Test that valid object keys pass validation."""
        entity_id = uuid.uuid4()
        valid_keys = [
            f"vidya-assets/test-tenant/submission/{entity_id}/{uuid.uuid4()}-file.pdf",
            f"vidya-assets/my-org/research_doc/{entity_id}/{uuid.uuid4()}-report.docx",
            f"vidya-assets/uni-1/viva_recording/{entity_id}/{uuid.uuid4()}-video.mp4",
            f"vidya-assets/acme-corp/course_kit/{entity_id}/{uuid.uuid4()}-slides.pdf",
        ]

        for key in valid_keys:
            assert StorageRepository._validate_object_key(key), f"Should validate: {key}"

    def test_invalid_object_keys(self):
        """Test that invalid object keys fail validation."""
        invalid_keys = [
            "invalid/format",
            "vidya-assets/test",
            "vidya-assets/test-tenant/invalid_type/id/file.pdf",
            "../../../etc/passwd",
            "vidya-assets/test-tenant/submission/not-a-uuid/file.pdf",
            "vidya-assets/test-tenant/submission//double-slash.pdf",
            "s3://bucket/key",  # AWS S3 style, not our format
            "",
            "vidya-assets/test-tenant/SUBMISSION/id/file.pdf",  # uppercase entity type
        ]

        for key in invalid_keys:
            assert not StorageRepository._validate_object_key(key), f"Should reject: {key}"

    def test_key_with_special_chars_in_filename(self):
        """Test that keys with special characters in filename are validated."""
        entity_id = uuid.uuid4()
        # Hyphens and dots are allowed in filenames
        key = f"vidya-assets/test-tenant/submission/{entity_id}/{uuid.uuid4()}-my-file_2024.05.07.pdf"
        assert StorageRepository._validate_object_key(key)

    def test_key_rejects_path_traversal(self):
        """Test that path traversal attempts are rejected."""
        entity_id = uuid.uuid4()
        malicious_keys = [
            f"vidya-assets/test-tenant/../submission/{entity_id}/{uuid.uuid4()}-file.pdf",
            f"vidya-assets/test-tenant/submission/{entity_id}/../../etc/passwd",
            f"vidya-assets/test-tenant/submission/{entity_id}/.../.../file.pdf",
        ]

        for key in malicious_keys:
            assert not StorageRepository._validate_object_key(key), f"Should reject path traversal: {key}"


class TestEntityTypeEnum:
    """Test storage entity type enum."""

    def test_entity_types_exist(self):
        """Test that all expected entity types are defined."""
        from app.core.storage.models import StorageEntityType

        expected_types = ["submission", "research_doc", "course_kit", "viva_recording"]
        for entity_type in expected_types:
            assert entity_type in [e.value for e in StorageEntityType]

    def test_entity_type_values(self):
        """Test entity type enum values."""
        from app.core.storage.models import StorageEntityType

        assert StorageEntityType.SUBMISSION.value == "submission"
        assert StorageEntityType.RESEARCH_DOC.value == "research_doc"
        assert StorageEntityType.COURSE_KIT.value == "course_kit"
        assert StorageEntityType.VIVA_RECORDING.value == "viva_recording"
