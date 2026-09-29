"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertCircle, RotateCcw, Home } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error captured by ErrorBoundary:", error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex min-h-[400px] w-full flex-col items-center justify-center p-6 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-danger/10 text-danger border border-danger/20 mb-4">
            <AlertCircle className="h-7 w-7" />
          </div>
          <h2 className="text-lg font-bold tracking-tight text-foreground sm:text-xl">
            Something went wrong
          </h2>
          <p className="mt-1.5 max-w-md text-xs text-text-secondary sm:text-sm">
            An unexpected error occurred while rendering this component. You can retry or return to the dashboard.
          </p>

          {this.state.error && (
            <div className="mt-4 max-w-lg overflow-hidden rounded-xl border border-border bg-surface-2 p-3 text-left">
              <p className="font-mono text-xs text-danger break-all">
                {this.state.error.message || "Unknown error"}
              </p>
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Button
              variant="default"
              onClick={this.handleReset}
              className="inline-flex items-center gap-2 text-xs"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Try Again
            </Button>
            <Link href="/dashboard">
              <Button
                variant="outline"
                className="inline-flex items-center gap-2 text-xs"
              >
                <Home className="h-3.5 w-3.5" />
                Return to Dashboard
              </Button>
            </Link>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
