"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type UploadDropzoneProps = {
  onUpload: (file: File) => Promise<void>;
  disabled?: boolean;
};

export function UploadDropzone({ onUpload, disabled }: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const isBusy = progress > 0 && progress < 100;

  const progressLabel = useMemo(() => {
    if (progress === 100) return "Complete";
    if (progress > 0) return `Uploading ${progress}%`;
    return "Upload meeting audio";
  }, [progress]);

  const triggerUpload = async (file: File) => {
    if (disabled || isBusy) return;
    setProgress(12);
    const timer = window.setInterval(() => {
      setProgress((prev) => (prev < 88 ? prev + 6 : prev));
    }, 280);
    try {
      await onUpload(file);
      setProgress(100);
      window.setTimeout(() => setProgress(0), 900);
    } finally {
      window.clearInterval(timer);
    }
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
          <p className="text-xs text-text-tertiary">Drop .mp3, .wav, .m4a, .ogg, or click to browse.</p>
        </div>
      </div>

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
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".mp3,.wav,.m4a,.flac,.aac,.ogg,.webm"
        className="hidden"
        onChange={onSelectFile}
      />
    </div>
  );
}
