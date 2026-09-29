"use client";

import { useEffect } from "react";
import { AlertCircle, RotateCcw, Home } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Route execution error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] w-full flex-col items-center justify-center p-6 text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-danger/10 text-danger border border-danger/20 mb-4">
        <AlertCircle className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
        Application Error
      </h2>
      <p className="mt-2 max-w-md text-xs text-text-secondary sm:text-sm">
        An unexpected error occurred while loading this view. You can reload or navigate back to safety.
      </p>

      {error?.message && (
        <div className="mt-4 max-w-md overflow-hidden rounded-xl border border-border bg-surface-2 p-3 text-left">
          <p className="font-mono text-xs text-danger break-all">
            {error.message}
          </p>
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Button
          variant="default"
          onClick={() => reset()}
          className="inline-flex items-center gap-2 text-xs"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Retry View
        </Button>
        <Link href="/dashboard">
          <Button
            variant="outline"
            className="inline-flex items-center gap-2 text-xs"
          >
            <Home className="h-3.5 w-3.5" />
            Go to Dashboard
          </Button>
        </Link>
      </div>
    </div>
  );
}
