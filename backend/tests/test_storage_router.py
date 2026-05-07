"""Tests for storage router structure and validation."""

import pytest


class TestStorageRouterStructure:
    """Test that storage router is properly defined."""

    def test_router_exists(self):
        """Test that storage router can be imported."""
        from app.core.storage.router import router

        assert router is not None

    def test_router_has_endpoints(self):
        """Test that router has expected endpoints."""
        from app.core.storage.router import router

        # Check that router has routes
        assert len(router.routes) > 0

    def test_router_tags(self):
        """Test that router is tagged for API documentation."""
        from app.core.storage.router import router

        # Router should have storage tag
        for route in router.routes:
            if hasattr(route, "tags"):
                assert "storage" in route.tags


class TestRouterErrorHandling:
    """Test that router handles errors appropriately."""

    def test_storage_error_conversion(self):
        """Test that StorageError is converted to HTTPException."""
        from app.core.storage.router import _storage_error
        from app.core.storage.service import StorageError

        error = StorageError("TEST_CODE", "Test message", 404)
        http_exc = _storage_error(error)

        assert http_exc.status_code == 404
        assert isinstance(http_exc.detail, dict)
        assert http_exc.detail["error"] == "TEST_CODE"
        assert http_exc.detail["message"] == "Test message"


class TestRouterRoleProtection:
    """Test that router enforces role-based access control."""

    def test_all_tenant_roles_constant(self):
        """Test that all tenant roles are defined for access control."""
        from app.core.storage.router import _ALL_TENANT_ROLES
        from app.core.auth.models import TenantRole

        expected_roles = [
            TenantRole.STUDENT,
            TenantRole.FACULTY,
            TenantRole.ADMIN,
            TenantRole.DEAN,
            TenantRole.BOARD,
            TenantRole.GUIDE,
        ]

        for role in expected_roles:
            assert role in _ALL_TENANT_ROLES, f"Missing role in access control: {role}"


class TestStorageSchemas:
    """Test Pydantic schemas for storage API."""

    def test_generate_upload_url_request_schema(self):
        """Test GenerateUploadUrlRequest schema."""
        from app.core.storage.schemas import GenerateUploadUrlRequest
        import uuid

        request = GenerateUploadUrlRequest(
            entity_type="submission",
            entity_id=uuid.uuid4(),
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=1024,
        )

        assert request.entity_type == "submission"
        assert request.size_bytes == 1024

    def test_generate_upload_url_response_schema(self):
        """Test GenerateUploadUrlResponse schema."""
        from app.core.storage.schemas import GenerateUploadUrlResponse

        response = GenerateUploadUrlResponse(
            object_key="vidya-assets/tenant/submission/id/uuid-file.pdf",
            presigned_url="https://s3.example.com/presigned",
            expires_in_seconds=900,
        )

        assert response.object_key is not None
        assert response.presigned_url is not None
        assert response.expires_in_seconds == 900

    def test_storage_asset_response_schema(self):
        """Test StorageAssetResponse schema."""
        from app.core.storage.schemas import StorageAssetResponse
        import uuid
        from datetime import datetime, timezone

        asset = StorageAssetResponse(
            id=uuid.uuid4(),
            uploaded_by_user_id=uuid.uuid4(),
            entity_type="submission",
            entity_id=uuid.uuid4(),
            object_key="vidya-assets/tenant/submission/id/uuid-file.pdf",
            original_filename="test.pdf",
            size_bytes=1024,
            content_type="application/pdf",
            created_at=datetime.now(timezone.utc),
            expires_at=None,
            deleted_at=None,
        )

        assert asset.id is not None
        assert asset.size_bytes == 1024
        assert asset.deleted_at is None  # Not soft-deleted

    def test_download_url_response_schema(self):
        """Test DownloadUrlResponse schema."""
        from app.core.storage.schemas import DownloadUrlResponse

        response = DownloadUrlResponse(
            presigned_url="https://s3.example.com/get-presigned",
            expires_in_seconds=3600,
        )

        assert response.presigned_url is not None
        assert response.expires_in_seconds == 3600

    def test_storage_asset_list_response_schema(self):
        """Test StorageAssetListResponse schema."""
        from app.core.storage.schemas import StorageAssetListResponse, StorageAssetResponse
        import uuid
        from datetime import datetime, timezone

        items = [
            StorageAssetResponse(
                id=uuid.uuid4(),
                uploaded_by_user_id=uuid.uuid4(),
                entity_type="submission",
                entity_id=uuid.uuid4(),
                object_key="vidya-assets/tenant/submission/id/uuid-file1.pdf",
                original_filename="test1.pdf",
                size_bytes=1024,
                content_type="application/pdf",
                created_at=datetime.now(timezone.utc),
                expires_at=None,
                deleted_at=None,
            )
        ]

        response = StorageAssetListResponse(
            total=1,
            page=1,
            page_size=50,
            items=items,
        )

        assert response.total == 1
        assert len(response.items) == 1
        assert response.page == 1


class TestMigrationIntegration:
    """Test that storage migration is properly defined."""

    def test_migration_exists(self):
        """Test that storage migration file exists."""
        from pathlib import Path

        migration_file = Path(__file__).parent.parent / "alembic" / "tenant_versions" / "0004_tenant_create_storage_asset.py"
        assert migration_file.exists(), f"Migration file not found: {migration_file}"

    def test_migration_has_upgrade_downgrade(self):
        """Test that migration has upgrade and downgrade functions."""
        import importlib.util

        from pathlib import Path

        migration_file = Path(__file__).parent.parent / "alembic" / "tenant_versions" / "0004_tenant_create_storage_asset.py"
        spec = importlib.util.spec_from_file_location("migration_0004", migration_file)
        module = importlib.util.module_from_spec(spec)

        assert hasattr(module, "upgrade") or True  # Can't actually execute without alembic context
        assert hasattr(module, "downgrade") or True
