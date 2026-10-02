"""Tests for StorageService (Cloudflare R2 / AWS S3 and Local fallback)."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from core.config import settings
from core.storage import StorageService


@pytest.fixture
def temp_audio_file():
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"ID3_MOCK_AUDIO_DATA_FOR_TESTING")
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_local_storage_lifecycle(temp_audio_file):
    """Verify local storage backend upload, exists, download, and delete."""
    service = StorageService()

    storage_key = "audio/test_user/test_audio.mp3"
    uploaded_key = await service.upload_file(temp_audio_file, storage_key)
    assert uploaded_key == storage_key

    # Exists check
    assert await service.file_exists(storage_key) is True

    # Download check
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as dl_file:
        dl_path = dl_file.name
    try:
        success = await service.download_file(storage_key, dl_path)
        assert success is True
        with open(dl_path, "rb") as f:
            data = f.read()
        assert data == b"ID3_MOCK_AUDIO_DATA_FOR_TESTING"
    finally:
        if os.path.exists(dl_path):
            os.remove(dl_path)

    # Delete check
    del_success = await service.delete_file(storage_key)
    assert del_success is True
    assert await service.file_exists(storage_key) is False


@pytest.mark.asyncio
async def test_s3_storage_configured(temp_audio_file):
    """Verify S3/R2 upload and presigned URL generation with mocked boto3."""
    service = StorageService()

    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://r2.cloudflarestorage.com/my-bucket/audio/test.mp3?token=mock123"

    with patch.object(settings, "storage_backend", "s3"), \
         patch.object(settings, "s3_bucket_name", "test-bucket"), \
         patch.object(settings, "s3_access_key_id", "test-key-id"), \
         patch.object(settings, "s3_secret_access_key", "test-secret-key"), \
         patch.object(service, "_get_s3_client", return_value=mock_client):

        assert service.is_s3_configured() is True

        key = await service.upload_file(temp_audio_file, "audio/user1/test.mp3")
        assert key == "audio/user1/test.mp3"
        mock_client.upload_file.assert_called_once()

        presigned_url = await service.get_presigned_url("audio/user1/test.mp3", expires_in=1800)
        assert presigned_url == "https://r2.cloudflarestorage.com/my-bucket/audio/test.mp3?token=mock123"
        mock_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "test-bucket", "Key": "audio/user1/test.mp3"},
            ExpiresIn=1800,
        )


def test_s3_path_style_for_custom_endpoint():
    """Verify that path-style addressing is configured for custom endpoints (Supabase/MinIO)."""
    service = StorageService()

    with patch.object(settings, "storage_backend", "s3"), \
         patch.object(settings, "s3_bucket_name", "test-bucket"), \
         patch.object(settings, "s3_access_key_id", "test-key-id"), \
         patch.object(settings, "s3_secret_access_key", "test-secret-key"), \
         patch.object(settings, "s3_endpoint_url", "https://custom.storage.supabase.co/s3"), \
         patch("boto3.client") as mock_boto:

        client = service._get_s3_client()
        mock_boto.assert_called_once()
        _, kwargs = mock_boto.call_args
        assert kwargs["config"].s3["addressing_style"] == "path"

