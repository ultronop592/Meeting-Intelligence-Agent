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

    with patch.object(service, "is_s3_configured", return_value=False):
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
        mock_client.generate_presigned_url.assert_called_with(
            ClientMethod="get_object",
            Params={"Bucket": "test-bucket", "Key": "audio/user1/test.mp3"},
            ExpiresIn=1800,
        )

        upload_presigned = await service.get_presigned_upload_url("audio/user1/test.mp3", content_type="audio/webm", expires_in=3600)
        assert upload_presigned == "https://r2.cloudflarestorage.com/my-bucket/audio/test.mp3?token=mock123"
        mock_client.generate_presigned_url.assert_called_with(
            ClientMethod="put_object",
            Params={"Bucket": "test-bucket", "Key": "audio/user1/test.mp3", "ContentType": "audio/webm"},
            ExpiresIn=3600,
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


class MockAsyncStream:
    def __init__(self, data: bytes, chunk_size: int = 1024 * 1024):
        self.data = data
        self.chunk_size = chunk_size
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.data):
            return b""
        actual_size = self.chunk_size if size <= 0 else min(size, self.chunk_size)
        chunk = self.data[self.offset : self.offset + actual_size]
        self.offset += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_stream_upload_local():
    """Verify stream_upload fallback to local disk writing without S3."""
    service = StorageService()
    test_data = b"STREAMED_AUDIO_CHUNK_DATA_FOR_TESTING" * 100
    mock_file = MockAsyncStream(test_data)

    with patch.object(service, "is_s3_configured", return_value=False):
        storage_key = "audio/stream_test/sample.mp3"
        saved_key, size = await service.stream_upload(mock_file, storage_key)
        assert saved_key == storage_key
        assert size == len(test_data)

        # Check file exists and clean up
        assert await service.file_exists(storage_key) is True
        await service.delete_file(storage_key)


@pytest.mark.asyncio
async def test_stream_upload_s3_single_part():
    """Verify small files (<= 5MB) use put_object directly without multipart overhead."""
    service = StorageService()
    test_data = b"A" * (2 * 1024 * 1024)  # 2 MB
    mock_file = MockAsyncStream(test_data)
    mock_client = MagicMock()

    with patch.object(settings, "storage_backend", "s3"), \
         patch.object(settings, "s3_bucket_name", "test-bucket"), \
         patch.object(settings, "s3_access_key_id", "test-key-id"), \
         patch.object(settings, "s3_secret_access_key", "test-secret-key"), \
         patch.object(service, "_get_s3_client", return_value=mock_client):

        saved_key, size = await service.stream_upload(mock_file, "audio/test.mp3", content_type="audio/mpeg")
        assert saved_key == "audio/test.mp3"
        assert size == len(test_data)
        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="audio/test.mp3",
            Body=test_data,
            ContentType="audio/mpeg",
        )
        mock_client.create_multipart_upload.assert_not_called()


@pytest.mark.asyncio
async def test_stream_upload_s3_multipart():
    """Verify files > 5MB trigger S3 multipart upload and complete properly."""
    service = StorageService()
    test_data = b"B" * (6 * 1024 * 1024)  # 6 MB (triggers 5MB part + 1MB final part)
    mock_file = MockAsyncStream(test_data)
    mock_client = MagicMock()
    mock_client.create_multipart_upload.return_value = {"UploadId": "mock-mpu-id-123"}
    mock_client.upload_part.side_effect = [
        {"ETag": '"etag-part-1"'},
        {"ETag": '"etag-part-2"'},
    ]

    with patch.object(settings, "storage_backend", "s3"), \
         patch.object(settings, "s3_bucket_name", "test-bucket"), \
         patch.object(settings, "s3_access_key_id", "test-key-id"), \
         patch.object(settings, "s3_secret_access_key", "test-secret-key"), \
         patch.object(service, "_get_s3_client", return_value=mock_client):

        saved_key, size = await service.stream_upload(mock_file, "audio/large.mp3", content_type="audio/mpeg")
        assert saved_key == "audio/large.mp3"
        assert size == len(test_data)

        mock_client.create_multipart_upload.assert_called_once_with(
            Bucket="test-bucket",
            Key="audio/large.mp3",
            ContentType="audio/mpeg",
        )
        assert mock_client.upload_part.call_count == 2
        mock_client.complete_multipart_upload.assert_called_once_with(
            Bucket="test-bucket",
            Key="audio/large.mp3",
            UploadId="mock-mpu-id-123",
            MultipartUpload={
                "Parts": [
                    {"PartNumber": 1, "ETag": '"etag-part-1"'},
                    {"PartNumber": 2, "ETag": '"etag-part-2"'},
                ]
            },
        )


@pytest.mark.asyncio
async def test_stream_upload_s3_abort_on_error():
    """Verify multipart upload is aborted if an error occurs mid-stream."""
    service = StorageService()
    test_data = b"C" * (6 * 1024 * 1024)
    mock_file = MockAsyncStream(test_data)
    mock_client = MagicMock()
    mock_client.create_multipart_upload.return_value = {"UploadId": "mock-abort-id-456"}
    mock_client.upload_part.side_effect = RuntimeError("Network connection reset mid-upload")

    with patch.object(settings, "storage_backend", "s3"), \
         patch.object(settings, "s3_bucket_name", "test-bucket"), \
         patch.object(settings, "s3_access_key_id", "test-key-id"), \
         patch.object(settings, "s3_secret_access_key", "test-secret-key"), \
         patch.object(service, "_get_s3_client", return_value=mock_client):

        with pytest.raises(RuntimeError, match="Network connection reset mid-upload"):
            await service.stream_upload(mock_file, "audio/fail.mp3")

        mock_client.abort_multipart_upload.assert_called_once_with(
            Bucket="test-bucket",
            Key="audio/fail.mp3",
            UploadId="mock-abort-id-456",
        )


