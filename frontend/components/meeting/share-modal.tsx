"use client";

import { useEffect, useState } from "react";
import {
  Share2,
  Copy,
  Check,
  ExternalLink,
  Globe,
  Clock,
  ShieldAlert,
  X,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { meetingApi } from "@/lib/api/meetings";
import type { ShareLinkResponse } from "@/types/api";

interface ShareModalProps {
  isOpen: boolean;
  onClose: () => void;
  meetingId: string;
  meetingTitle: string;
}

export function ShareModal({ isOpen, onClose, meetingId, meetingTitle }: ShareModalProps) {
  const [shareData, setShareData] = useState<ShareLinkResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [expiresInDays, setExpiresInDays] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch current share status when modal opens
  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setIsLoading(true);
    meetingApi
      .getShareLink(meetingId)
      .then((data) => {
        setShareData(data);
      })
      .catch((err) => {
        console.error("Failed to load share status:", err);
        setError("Unable to load current share status.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [isOpen, meetingId]);

  if (!isOpen) return null;

  const fullShareUrl =
    typeof window !== "undefined" && shareData?.share_token
      ? `${window.location.origin}/share/${shareData.share_token}`
      : "";

  const handleToggleShare = async (enable: boolean) => {
    setIsUpdating(true);
    setError(null);
    try {
      if (enable) {
        const res = await meetingApi.createShareLink(meetingId, expiresInDays);
        setShareData(res);
      } else {
        await meetingApi.revokeShareLink(meetingId);
        setShareData((prev) =>
          prev ? { ...prev, is_publicly_shared: false } : null
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update share link";
      setError(msg);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleCopy = async () => {
    if (!fullShareUrl) return;
    try {
      await navigator.clipboard.writeText(fullShareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError("Failed to copy link to clipboard.");
    }
  };

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return "Never";
    try {
      return new Date(isoString).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900/95 p-6 shadow-2xl backdrop-blur-md">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 mb-5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-500/25 text-cyan-400">
            <Share2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Share Meeting</h2>
            <p className="text-xs text-slate-400 truncate max-w-xs">{meetingTitle}</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-10 gap-2">
            <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
            <p className="text-xs text-slate-400">Checking link status...</p>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Toggle Card */}
            <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="flex items-start gap-3">
                <Globe
                  className={`h-5 w-5 mt-0.5 ${
                    shareData?.is_publicly_shared ? "text-cyan-400" : "text-slate-500"
                  }`}
                />
                <div>
                  <h4 className="text-sm font-medium text-slate-200">Public Link Access</h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {shareData?.is_publicly_shared
                      ? "Anyone with the link can view summary and listen to audio without signing in."
                      : "Only authorized members can currently view this meeting."}
                  </p>
                </div>
              </div>

              <button
                type="button"
                disabled={isUpdating}
                onClick={() => handleToggleShare(!shareData?.is_publicly_shared)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  shareData?.is_publicly_shared ? "bg-cyan-500" : "bg-slate-700"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    shareData?.is_publicly_shared ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* When Public Link is Active */}
            {shareData?.is_publicly_shared && (
              <div className="space-y-4 rounded-xl border border-cyan-500/20 bg-cyan-500/[0.03] p-4">
                {/* Link Box */}
                <div>
                  <label className="text-xs font-medium text-slate-300 mb-1.5 block">
                    Public Share URL
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={fullShareUrl}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono text-cyan-300 focus:outline-none select-all"
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCopy}
                      className="shrink-0 h-9 px-3 border-cyan-500/30 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20"
                    >
                      {copied ? (
                        <>
                          <Check className="h-4 w-4 mr-1 text-emerald-400" />
                          Copied
                        </>
                      ) : (
                        <>
                          <Copy className="h-4 w-4 mr-1" />
                          Copy
                        </>
                      )}
                    </Button>
                    <a
                      href={fullShareUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-center h-9 w-9 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
                      title="Open in new tab"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>
                </div>

                {/* Expiration Settings */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs text-slate-300">
                  <div className="flex items-center gap-1.5 text-slate-400">
                    <Clock className="h-4 w-4 text-cyan-400" />
                    <span>Expires:</span>
                    <span className="font-semibold text-slate-200">
                      {formatDate(shareData?.expires_at)}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-slate-400">Change:</span>
                    <select
                      value={expiresInDays ?? "never"}
                      onChange={(e) => {
                        const val = e.target.value === "never" ? null : Number(e.target.value);
                        setExpiresInDays(val);
                        meetingApi.createShareLink(meetingId, val).then((res) => setShareData(res));
                      }}
                      className="rounded bg-slate-900 border border-slate-700 px-2 py-1 text-xs text-slate-200 focus:outline-none"
                    >
                      <option value="never">Never</option>
                      <option value="7">7 Days</option>
                      <option value="14">14 Days</option>
                      <option value="30">30 Days</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* Security note */}
            <div className="flex items-start gap-2 text-xs text-slate-500 bg-slate-950/40 p-3 rounded-lg border border-slate-800/60">
              <ShieldAlert className="h-4 w-4 shrink-0 text-slate-400 mt-0.5" />
              <span>
                Shared views are strictly read-only. External recipients cannot edit action items,
                delete data, or access other meetings in your workspace.
              </span>
            </div>
          </div>
        )}

        {/* Modal Footer */}
        <div className="mt-6 flex items-center justify-between pt-4 border-t border-slate-800">
          {shareData?.is_publicly_shared ? (
            <button
              onClick={() => handleToggleShare(false)}
              disabled={isUpdating}
              className="text-xs text-red-400 hover:text-red-300 hover:underline"
            >
              Revoke link
            </button>
          ) : (
            <div />
          )}

          <Button variant="ghost" size="sm" onClick={onClose} className="text-slate-300">
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
