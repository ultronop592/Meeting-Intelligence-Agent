"""Object Storage Service for Meeting Audio Files.

Supports Cloudflare R2, AWS S3, and MinIO with seamless local filesystem fallback.
Provides presigned URLs for direct client streaming and thread-offloaded async operations.
"""

import asyncio
import logging
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Optional

from core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Manages audio file persistence across Cloudflare R2, AWS S3, or local disk."""

    def __init__(self) -> None:
        self._s3_client = None
        self._init_lock = asyncio.Lock()

    def is_s3_configured(self) -> bool:
        """Returns True if S3/R2 object storage credentials and bucket are configured."""
        backend = (settings.storage_backend or "local").lower().strip()
        if backend != "s3":
            return False
        has_bucket = bool(settings.s3_bucket_name and settings.s3_bucket_name.strip())
        has_keys = bool(
            settings.s3_access_key_id
            and settings.s3_access_key_id.strip()
            and settings.s3_secret_access_key
            and settings.s3_secret_access_key.strip()
        )
        return has_bucket and has_keys

    async def _write_to_local_disk(
        self,
        storage_key: str,
        buffer: bytearray,
        file_obj=None,
        max_bytes: int = 1024 * 1024 * 1024,
        current_size: int = 0,
    ) -> tuple[str, int]:
        """Save buffered data + any remaining stream to local disk."""
        os.makedirs(settings.upload_dir, exist_ok=True)
        dest_path = os.path.join(settings.upload_dir, storage_key)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        total_size = current_size or len(buffer)

        with open(dest_path, "wb") as f:
            if buffer:
                f.write(buffer)
            if file_obj:
                while True:
                    chunk = await file_obj.read(1024 * 1024)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > max_bytes:
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        raise ValueError(f"Uploaded file exceeds maximum allowed size of {max_bytes} bytes")
                    f.write(chunk)
        if total_size == 0:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            raise ValueError("Uploaded file is empty")
        logger.info("Saved %d bytes to local disk: %s", total_size, dest_path)
        return storage_key, total_size

    def _get_s3_client(self):
        """Synchronously get or initialize the boto3 S3 client."""
        if self._s3_client is not None:
            return self._s3_client

        if not self.is_s3_configured():
            return None

        try:
            import boto3
            from botocore.config import Config

            addressing_style = "path" if settings.s3_endpoint_url else "virtual"
            boto_config = Config(
                signature_version="s3v4",
                s3={"addressing_style": addressing_style},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                # Prevent SSL EOF on slow / rate-limited S3-compatible providers
                # (e.g. Supabase Storage) by enforcing explicit socket timeouts.
                connect_timeout=10,   # seconds to establish TCP connection
                read_timeout=300,     # seconds to wait for data on large uploads
                retries={"max_attempts": 3, "mode": "standard"},
            )
            client_kwargs = {
                "service_name": "s3",
                "aws_access_key_id": settings.s3_access_key_id.strip(),
                "aws_secret_access_key": settings.s3_secret_access_key.strip(),
                "region_name": settings.s3_region_name.strip() or "auto",
                "config": boto_config,
            }

            if settings.s3_endpoint_url and settings.s3_endpoint_url.strip():
                client_kwargs["endpoint_url"] = settings.s3_endpoint_url.strip()

            self._s3_client = boto3.client(**client_kwargs)

            def _clean_s3_headers(request, **kwargs):
                if "Transfer-Encoding" in request.headers:
                    del request.headers["Transfer-Encoding"]
                if request.headers.get("Content-Encoding") == "aws-chunked":
                    del request.headers["Content-Encoding"]
                if "Content-Length" not in request.headers and hasattr(request, "body") and request.body is not None:
                    try:
                        request.headers["Content-Length"] = str(len(request.body))
                    except (TypeError, AttributeError):
                        pass

            self._s3_client.meta.events.register("before-send.s3.UploadPart", _clean_s3_headers)
            self._s3_client.meta.events.register("before-send.s3.PutObject", _clean_s3_headers)

            logger.info(
                "S3/R2 storage client initialized (bucket=%s, endpoint=%s)",
                settings.s3_bucket_name,
                settings.s3_endpoint_url or "aws-default",
            )
            return self._s3_client
        except Exception as exc:
            logger.error("Failed to initialize boto3 S3 client: %s", exc)
            return None

    def _sync_upload(self, local_path: str, storage_key: str, content_type: Optional[str] = None) -> str:
        client = self._get_s3_client()
        if client:
            extra_args = {}
            c_type = content_type or mimetypes.guess_type(local_path)[0] or "application/octet-stream"
            extra_args["ContentType"] = c_type
            client.upload_file(
                Filename=local_path,
                Bucket=settings.s3_bucket_name.strip(),
                Key=storage_key,
                ExtraArgs=extra_args,
            )
            logger.info("Uploaded %s to S3 bucket %s with key %s", local_path, settings.s3_bucket_name, storage_key)
            return storage_key

        # Local storage fallback
        os.makedirs(settings.upload_dir, exist_ok=True)
        dest_path = os.path.join(settings.upload_dir, storage_key)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        if os.path.abspath(local_path) != os.path.abspath(dest_path):
            shutil.copy2(local_path, dest_path)
            logger.info("Persisted audio locally to %s", dest_path)
        return storage_key

    async def upload_file(
        self,
        local_path: str,
        storage_key: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Uploads a local audio file to S3/R2 or local persistent directory."""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Source file not found: {local_path}")
        return await asyncio.to_thread(self._sync_upload, local_path, storage_key, content_type)

    async def stream_upload(
        self,
        file_obj,
        storage_key: str,
        content_type: Optional[str] = None,
        max_size_bytes: Optional[int] = None,
    ) -> tuple[str, int]:
        """Stream an incoming file directly to S3/R2 using multipart upload without disk buffering.

        Falls back to streamed local disk writing if S3 is not configured.
        Returns:
            tuple[storage_key, total_bytes_uploaded]
        """
        c_type = content_type or "application/octet-stream"
        max_bytes = max_size_bytes or settings.max_upload_size_bytes

        client = self._get_s3_client()
        if not client:
            return await self._write_to_local_disk(storage_key, bytearray(), file_obj, max_bytes)

        # S3 / Cloudflare R2 / Supabase S3 multipart streaming
        bucket = settings.s3_bucket_name.strip()
        PART_SIZE = 5 * 1024 * 1024  # 5 MB S3 multipart minimum
        READ_CHUNK_SIZE = 1024 * 1024  # 1 MB reads
        total_size = 0
        buffer = bytearray()

        # Step 1: Read up to PART_SIZE to determine if multipart is needed
        while len(buffer) < PART_SIZE:
            chunk = await file_obj.read(READ_CHUNK_SIZE)
            if not chunk:
                break
            buffer.extend(chunk)
            total_size += len(chunk)
            if total_size > max_bytes:
                raise ValueError(f"Uploaded file exceeds maximum allowed size of {max_bytes} bytes")

        if total_size == 0:
            raise ValueError("Uploaded file is empty")

        # Case A: File is smaller than or equal to 5 MB -> single put_object
        first_extra_chunk = await file_obj.read(READ_CHUNK_SIZE)
        if not first_extra_chunk:
            try:
                await asyncio.to_thread(
                    client.put_object,
                    Bucket=bucket,
                    Key=storage_key,
                    Body=bytes(buffer),
                    ContentType=c_type,
                )
                logger.info("Directly put %d bytes to S3 key %s (single part)", total_size, storage_key)
                return storage_key, total_size
            except Exception as s3_err:
                err_str = str(s3_err)
                if "540" in err_str or "paused" in err_str.lower():
                    logger.warning(
                        "Supabase S3 returned HTTP 540 (Project paused) for key %s. "
                        "Gracefully falling back to local disk storage.",
                        storage_key,
                    )
                    return await self._write_to_local_disk(storage_key, buffer, None, max_bytes, total_size)
                raise

        # Case B: File is larger than 5 MB
        buffer.extend(first_extra_chunk)
        total_size += len(first_extra_chunk)

        # If the storage provider doesn't support multipart (e.g. Supabase),
        # buffer the entire file and use a single put_object call.
        if not settings.s3_supports_multipart:
            SUPABASE_SINGLE_PUT_LIMIT = 50 * 1024 * 1024  # 50 MB
            endpoint_lower = (settings.s3_endpoint_url or "").lower()
            is_supabase = "supabase.co" in endpoint_lower

            logger.info(
                "Storage provider does not support multipart uploads — buffering full file for key %s",
                storage_key,
            )
            while True:
                chunk = await file_obj.read(READ_CHUNK_SIZE)
                if not chunk:
                    break
                buffer.extend(chunk)
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise ValueError(f"Uploaded file exceeds maximum allowed size of {max_bytes} bytes")
                # When using Supabase S3, files above 50 MB exceed Supabase's single PUT limit.
                # Gracefully fall back to local disk storage so the upload succeeds.
                if is_supabase and total_size > SUPABASE_SINGLE_PUT_LIMIT:
                    logger.warning(
                        "File exceeds Supabase S3 50 MB limit (%d bytes). "
                        "Gracefully falling back to local disk storage to complete upload.",
                        total_size,
                    )
                    return await self._write_to_local_disk(storage_key, buffer, file_obj, max_bytes, total_size)

            import io as _io
            try:
                await asyncio.to_thread(
                    client.put_object,
                    Bucket=bucket,
                    Key=storage_key,
                    Body=_io.BytesIO(bytes(buffer)),
                    ContentLength=total_size,
                    ContentType=c_type,
                )
                logger.info("Single put_object uploaded %d bytes to S3 key %s", total_size, storage_key)
                return storage_key, total_size
            except Exception as s3_err:
                err_str = str(s3_err)
                if "540" in err_str or "paused" in err_str.lower():
                    logger.warning(
                        "Supabase S3 returned HTTP 540 (Project paused) for key %s. "
                        "Gracefully falling back to local disk storage.",
                        storage_key,
                    )
                    return await self._write_to_local_disk(storage_key, buffer, None, max_bytes, total_size)
                raise

        mpu = await asyncio.to_thread(
            client.create_multipart_upload,
            Bucket=bucket,
            Key=storage_key,
            ContentType=c_type,
        )
        upload_id = mpu["UploadId"]
        parts = []
        part_number = 1

        try:
            # Upload first 5MB part
            part_body = bytes(buffer[:PART_SIZE])
            del buffer[:PART_SIZE]

            res = await asyncio.to_thread(
                client.upload_part,
                Bucket=bucket,
                Key=storage_key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=part_body,
            )
            parts.append({"PartNumber": part_number, "ETag": res["ETag"]})
            part_number += 1

            # Stream remaining parts as incoming chunks arrive
            while True:
                chunk = await file_obj.read(READ_CHUNK_SIZE)
                if not chunk:
                    break
                buffer.extend(chunk)
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise ValueError(f"Uploaded file exceeds maximum allowed size of {max_bytes} bytes")

                while len(buffer) >= PART_SIZE:
                    part_body = bytes(buffer[:PART_SIZE])
                    del buffer[:PART_SIZE]

                    res = await asyncio.to_thread(
                        client.upload_part,
                        Bucket=bucket,
                        Key=storage_key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=part_body,
                    )
                    parts.append({"PartNumber": part_number, "ETag": res["ETag"]})
                    part_number += 1

            # Upload final remaining bytes in buffer (can be < 5 MB)
            if len(buffer) > 0:
                res = await asyncio.to_thread(
                    client.upload_part,
                    Bucket=bucket,
                    Key=storage_key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=bytes(buffer),
                )
                parts.append({"PartNumber": part_number, "ETag": res["ETag"]})

            # Complete multipart upload
            await asyncio.to_thread(
                client.complete_multipart_upload,
                Bucket=bucket,
                Key=storage_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
            logger.info("Successfully streamed multipart upload (%d parts, %d bytes) to S3 key %s", len(parts), total_size, storage_key)
            return storage_key, total_size

        except Exception as exc:
            logger.warning("Aborting S3 multipart upload for key %s (upload_id=%s): %s", storage_key, upload_id, exc)
            try:
                await asyncio.to_thread(
                    client.abort_multipart_upload,
                    Bucket=bucket,
                    Key=storage_key,
                    UploadId=upload_id,
                )
            except Exception as abort_exc:
                logger.error("Failed to abort multipart upload: %s", abort_exc)
            raise

    def _sync_generate_presigned_url(self, storage_key: str, expires_in: int) -> Optional[str]:
        client = self._get_s3_client()
        if not client:
            return None
        try:
            url = client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": settings.s3_bucket_name.strip(),
                    "Key": storage_key,
                },
                ExpiresIn=expires_in,
            )
            return url
        except Exception as exc:
            logger.warning("Error generating presigned URL for key %s: %s", storage_key, exc)
            return None

    async def get_presigned_url(
        self,
        storage_key: str,
        expires_in: Optional[int] = None,
    ) -> Optional[str]:
        """Generates a presigned GET URL for streaming audio directly from Cloudflare R2 / S3."""
        if not self.is_s3_configured():
            return None
        exp = expires_in or settings.s3_presigned_url_expire_seconds
        return await asyncio.to_thread(self._sync_generate_presigned_url, storage_key, exp)

    def _sync_generate_presigned_upload_url(
        self,
        storage_key: str,
        content_type: str = "application/octet-stream",
        expires_in: int = 3600,
    ) -> Optional[str]:
        client = self._get_s3_client()
        if not client:
            return None
        try:
            params = {
                "Bucket": settings.s3_bucket_name.strip(),
                "Key": storage_key,
                "ContentType": content_type,
            }
            url = client.generate_presigned_url(
                ClientMethod="put_object",
                Params=params,
                ExpiresIn=expires_in,
            )
            return url
        except Exception as exc:
            logger.warning("Error generating presigned upload URL for key %s: %s", storage_key, exc)
            return None

    async def get_presigned_upload_url(
        self,
        storage_key: str,
        content_type: str = "application/octet-stream",
        expires_in: Optional[int] = None,
    ) -> Optional[str]:
        """Generates a presigned PUT URL allowing clients to upload audio directly to S3 / Cloudflare R2 / Supabase."""
        if not self.is_s3_configured():
            return None
        exp = expires_in or settings.s3_presigned_url_expire_seconds
        return await asyncio.to_thread(self._sync_generate_presigned_upload_url, storage_key, content_type, exp)

    def _sync_download(self, storage_key: str, destination_path: str) -> bool:
        client = self._get_s3_client()
        if client:
            try:
                os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                client.download_file(
                    Bucket=settings.s3_bucket_name.strip(),
                    Key=storage_key,
                    Filename=destination_path,
                )
                return True
            except Exception as exc:
                logger.error("Failed to download key %s from S3: %s", storage_key, exc)
                return False

        # Local storage fallback
        local_source = os.path.join(settings.upload_dir, storage_key)
        if os.path.exists(local_source):
            if os.path.abspath(local_source) != os.path.abspath(destination_path):
                os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                shutil.copy2(local_source, destination_path)
            return True
        return False

    async def download_file(self, storage_key: str, destination_path: str) -> bool:
        """Downloads an audio file from S3/R2 (or local store) to a target local path."""
        return await asyncio.to_thread(self._sync_download, storage_key, destination_path)

    def _sync_delete(self, storage_key: str) -> bool:
        client = self._get_s3_client()
        if client:
            try:
                client.delete_object(
                    Bucket=settings.s3_bucket_name.strip(),
                    Key=storage_key,
                )
                logger.info("Deleted S3 object %s from bucket %s", storage_key, settings.s3_bucket_name)
                return True
            except Exception as exc:
                logger.warning("Failed to delete S3 object %s: %s", storage_key, exc)
                return False

        # Local storage fallback
        local_path = os.path.join(settings.upload_dir, storage_key)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                return True
            except OSError as exc:
                logger.warning("Failed to remove local file %s: %s", local_path, exc)
                return False
        return True

    async def delete_file(self, storage_key: str) -> bool:
        """Deletes an audio file from S3/R2 or local directory."""
        return await asyncio.to_thread(self._sync_delete, storage_key)

    def _sync_exists(self, storage_key: str) -> bool:
        client = self._get_s3_client()
        if client:
            try:
                client.head_object(
                    Bucket=settings.s3_bucket_name.strip(),
                    Key=storage_key,
                )
                return True
            except Exception:
                return False

        # Local storage fallback
        local_path = os.path.join(settings.upload_dir, storage_key)
        return os.path.exists(local_path)

    async def file_exists(self, storage_key: str) -> bool:
        """Checks if a file exists in S3/R2 or local storage."""
        return await asyncio.to_thread(self._sync_exists, storage_key)


# Global singleton instance
storage_service = StorageService()
