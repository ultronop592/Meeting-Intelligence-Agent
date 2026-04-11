"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toUserErrorMessage } from "@/lib/api/client";

type UploadDropzoneProps = {
  onUpload: (
    file: File,
    onProgress: (percent: number) => void,
    signal?: AbortSignal
  ) => Promise<unknown>;
  disabled?: boolean;
  maxSizeMb?: number;
};

const ACCEPTED_EXTENSIONS = [
  ".mp3",
  ".wav",
  ".m4a",
  ".flac",
  ".aac",
  ".ogg",
  ".webm",
  ".mp4",
  ".mp.4",
];

export function UploadDropzone({
  onUpload,
  disabled,
  maxSizeMb = 1024,
}: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [selectedFileSizeMb, setSelectedFileSizeMb] = useState<number | null>(null);
  const [isCancelled, setIsCancelled] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const isBusy = progress > 0 && progress < 100;
  const maxBytes = maxSizeMb * 1024 * 1024;

  const progressLabel = useMemo(() => {
    if (progress === 100) return "Complete";
    if (progress > 0) return `Uploading ${progress}%`;
    if (disabled) return "Upload in progress";
    return "Upload meeting audio";
  }, [progress, disabled]);

  const validateFile = (file: File) => {
    const lowerName = file.name.toLowerCase();
    const isSupported = ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!isSupported) {
      return "Unsupported file type. Please upload a supported audio format.";
    }

    if (file.size > maxBytes) {
      return `File is too large. Maximum allowed size is ${maxSizeMb} MB (1 GB).`;
    }

    return null;
  };

  const triggerUpload = async (file: File) => {
    if (disabled || isBusy) return;

    const validationError = validateFile(file);
    if (validationError) {
      setErrorText(validationError);
      return;
    }

    setErrorText(null);
    setIsCancelled(false);
    setSelectedFileName(file.name);
    setSelectedFileSizeMb(Number((file.size / (1024 * 1024)).toFixed(2)));
    setProgress(0);
    abortRef.current = new AbortController();

    try {
      await onUpload(
        file,
        (percent) => setProgress(percent),
        abortRef.current.signal
      );
      setProgress(100);
      window.setTimeout(() => setProgress(0), 900);
    } catch (error) {
      setProgress(0);
      if (error instanceof DOMException && error.name === "AbortError") {
        setIsCancelled(true);
        setErrorText("Upload canceled.");
      } else {
        setErrorText(toUserErrorMessage(error));
      }
    } finally {
      abortRef.current = null;
    }
  };

  const cancelUpload = () => {
    abortRef.current?.abort();
  };

  const onSelectFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      await triggerUpload(file);
    }
  };

  const handleDrop = useCallback(
    async (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsDragging(false);
      const file = event.dataTransfer.files?.[0];
      if (file) {
        await triggerUpload(file);
      }
    },
    [disabled, isBusy]
  );

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-[16px] border border-dashed border-border bg-surface-2 p-5 transition-colors",
        isDragging ? "border-accent bg-surface-3" : "hover:border-accent/70"
      )}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled && !isBusy) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-[12px] border border-border bg-surface">
          <UploadCloud className="h-4 w-4 text-text-secondary" />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">{progressLabel}</p>
          <p className="text-xs text-text-tertiary">
            Supported: MP3, WAV, M4A, FLAC, AAC, OGG, WEBM, MP4.
          </p>
        </div>
      </div>

      <p className="rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-text-secondary">
        Upload limit: up to 1 GB per recording.
      </p>

      {selectedFileName ? (
        <p className="text-xs text-text-tertiary">
          Selected: <span className="font-medium text-foreground">{selectedFileName}</span>
          {selectedFileSizeMb !== null ? ` (${selectedFileSizeMb} MB)` : ""}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="h-2 flex-1 rounded-full bg-surface">
          <div
            className="h-2 rounded-full bg-accent transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled || isBusy}
          onClick={() => inputRef.current?.click()}
        >
          Choose file
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={!isBusy}
          onClick={cancelUpload}
        >
          Cancel upload
        </Button>
      </div>

      {errorText ? (
        <p
          className={cn(
            "rounded-[10px] border px-3 py-2 text-xs",
            isCancelled
              ? "border-border bg-surface text-text-secondary"
              : "border-danger/40 bg-danger/10 text-danger"
          )}
        >
          {errorText}
        </p>
      ) : null}

      <input
        ref={inputRef}
        type="file"
        accept=".mp3,.wav,.m4a,.flac,.aac,.ogg,.webm,.mp4,.mp.4"
        className="hidden"
        onChange={onSelectFile}
      />
    </div>
  );
}
