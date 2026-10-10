/**
 * TUS Resumable Upload — browser-to-Supabase direct upload.
 *
 * Uses tus-js-client to upload meeting audio files of any size (1 GB+)
 * directly to Supabase Storage without routing data through the FastAPI backend.
 *
 * Flow:
 *  1. POST /meeting/resumable-upload-token  => get TUS endpoint, auth token, storage key
 *  2. tus.Upload => streams file in 6 MB chunks directly to Supabase
 *  3. Return storage_key to caller for use with POST /meetings/process
 */

import * as tus from "tus-js-client";
import { apiRequest } from "@/lib/api/client";

type ResumableUploadTokenResponse = {
  resumable_upload_available: boolean;
  tus_endpoint?: string | null;
  auth_token?: string | null;
  storage_key?: string | null;
  bucket_name?: string | null;
  content_type?: string | null;
};

export type TusUploadResult = {
  storage_key: string;
  size_bytes: number;
  size_mb: number;
  filename: string;
};

/**
 * Upload a file directly to Supabase Storage via TUS resumable protocol.
 *
 * @param file          The File object selected by the user.
 * @param onProgress    Called with 0-100 percent as upload progresses.
 * @param signal        AbortSignal to cancel the upload.
 * @returns             Resolved with TusUploadResult on success.
 * @throws              On failure or if TUS is unavailable.
 */
export async function tusUploadToSupabase(
  file: File,
  onProgress?: (percent: number) => void,
  signal?: AbortSignal
): Promise<TusUploadResult> {
  // Step 1: Get TUS credentials from backend
  const tokenResp = await apiRequest<ResumableUploadTokenResponse>(
    "/meeting/resumable-upload-token",
    {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
      }),
    }
  );

  if (
    !tokenResp.resumable_upload_available ||
    !tokenResp.tus_endpoint ||
    !tokenResp.auth_token ||
    !tokenResp.storage_key ||
    !tokenResp.bucket_name
  ) {
    throw new Error("TUS resumable upload is not available on this server.");
  }

  const { tus_endpoint, auth_token, storage_key, bucket_name, content_type } = tokenResp;

  // Step 2: Upload via TUS
  return new Promise<TusUploadResult>((resolve, reject) => {
    let aborted = false;

    const upload = new tus.Upload(file, {
      endpoint: tus_endpoint,
      retryDelays: [0, 3000, 5000, 10000, 20000],
      chunkSize: 6 * 1024 * 1024, // Supabase-recommended 6 MB chunks
      headers: {
        Authorization: `Bearer ${auth_token}`,
        "x-upsert": "true",
      },
      metadata: {
        bucketName: bucket_name,
        objectName: storage_key,
        contentType: content_type || file.type || "application/octet-stream",
        cacheControl: "3600",
      },
      onProgress(bytesUploaded, bytesTotal) {
        if (!onProgress || aborted) return;
        const percent = Math.min(100, Math.round((bytesUploaded / bytesTotal) * 100));
        onProgress(percent);
      },
      onSuccess() {
        resolve({
          storage_key,
          size_bytes: file.size,
          size_mb: Number((file.size / (1024 * 1024)).toFixed(2)),
          filename: file.name,
        });
      },
      onError(error) {
        if (aborted) {
          reject(new DOMException("Upload aborted", "AbortError"));
        } else {
          reject(
            new Error(
              `TUS upload failed: ${error instanceof Error ? error.message : String(error)}`
            )
          );
        }
      },
    });

    // Wire AbortSignal to tus abort
    if (signal) {
      if (signal.aborted) {
        reject(new DOMException("Upload aborted", "AbortError"));
        return;
      }
      signal.addEventListener(
        "abort",
        () => {
          aborted = true;
          upload.abort(true).catch(() => {});
          reject(new DOMException("Upload aborted", "AbortError"));
        },
        { once: true }
      );
    }

    // Resume previous upload if fingerprint matches (handles page refreshes mid-upload)
    upload.findPreviousUploads().then((previous) => {
      if (previous.length > 0) {
        upload.resumeFromPreviousUpload(previous[0]);
      }
      upload.start();
    });
  });
}
