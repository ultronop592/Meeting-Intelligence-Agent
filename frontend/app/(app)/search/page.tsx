"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Search as SearchIcon,
  FileText,
  CheckCircle2,
  HelpCircle,
  ArrowRight,
  Sparkles,
  Loader2,
  Calendar,
  User,
  Filter,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  meetingApi,
  GlobalSearchResult,
  GlobalSearchMeetingResult,
  GlobalSearchActionResult,
  GlobalSearchDecisionResult,
} from "@/lib/api/meetings";

function SearchContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialQuery = searchParams.get("q") || "";

  const [query, setQuery] = useState(initialQuery);
  const [mode, setMode] = useState<"fulltext" | "semantic">("fulltext");
  const [activeTab, setActiveTab] = useState<"all" | "meetings" | "action_items" | "decisions">("all");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<GlobalSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialQuery) {
      performSearch(initialQuery, mode);
    }
  }, [initialQuery, mode]);

  const performSearch = async (searchTerm: string, searchMode: "fulltext" | "semantic") => {
    if (!searchTerm.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await meetingApi.searchGlobal(searchTerm.trim(), searchMode);
      setResults(res);
    } catch (err: any) {
      setError(err?.message || "Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    router.push(`/search?q=${encodeURIComponent(query.trim())}`);
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="space-y-4 rounded-2xl border border-border/80 bg-surface/60 p-6 backdrop-blur">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Global Intelligence Search</h1>
          <p className="text-sm text-text-secondary">
            Search across transcript text, meeting summaries, action items, and decisions.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative flex-1">
            <SearchIcon className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search meetings, decisions, or action owners..."
              className="w-full rounded-xl border border-border bg-surface-2 py-2.5 pl-10 pr-4 text-sm text-foreground outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
            />
          </div>

          <div className="flex items-center gap-2">
            {/* Full-text vs Semantic Toggle */}
            <div className="flex rounded-xl border border-border bg-surface-2 p-1 text-xs font-medium">
              <button
                type="button"
                onClick={() => setMode("fulltext")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  mode === "fulltext"
                    ? "bg-accent text-accent-foreground font-semibold shadow-sm"
                    : "text-text-secondary hover:text-foreground"
                }`}
              >
                Full-Text
              </button>
              <button
                type="button"
                onClick={() => setMode("semantic")}
                className={`flex items-center gap-1 rounded-lg px-3 py-1.5 transition ${
                  mode === "semantic"
                    ? "bg-accent text-accent-foreground font-semibold shadow-sm"
                    : "text-text-secondary hover:text-foreground"
                }`}
              >
                <Sparkles className="h-3 w-3" /> Semantic
              </button>
            </div>

            <Button type="submit" size="default" disabled={loading} className="gap-2 rounded-xl">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <SearchIcon className="h-4 w-4" />}
              Search
            </Button>
          </div>
        </form>
      </div>

      {/* Error state */}
      {error && (
        <Card className="border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </Card>
      )}

      {/* Results Section */}
      {results && (
        <div className="space-y-4">
          {/* Result Filter Tabs */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/80 pb-3">
            <div className="flex flex-wrap gap-2 text-sm font-medium">
              <button
                onClick={() => setActiveTab("all")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  activeTab === "all"
                    ? "bg-surface-2 text-foreground font-semibold border border-border"
                    : "text-text-secondary hover:text-foreground"
                }`}
              >
                All Results ({results.total_results})
              </button>
              <button
                onClick={() => setActiveTab("meetings")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  activeTab === "meetings"
                    ? "bg-surface-2 text-foreground font-semibold border border-border"
                    : "text-text-secondary hover:text-foreground"
                }`}
              >
                Meetings ({results.meetings.length})
              </button>
              <button
                onClick={() => setActiveTab("action_items")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  activeTab === "action_items"
                    ? "bg-surface-2 text-foreground font-semibold border border-border"
                    : "text-text-secondary hover:text-foreground"
                }`}
              >
                Action Items ({results.action_items.length})
              </button>
              <button
                onClick={() => setActiveTab("decisions")}
                className={`rounded-lg px-3 py-1.5 transition ${
                  activeTab === "decisions"
                    ? "bg-surface-2 text-foreground font-semibold border border-border"
                    : "text-text-secondary hover:text-foreground"
                }`}
              >
                Decisions ({results.decisions.length})
              </button>
            </div>

            <p className="text-xs text-text-tertiary">
              Showing search results for &quot;<span className="font-semibold text-foreground">{results.query}</span>&quot; ({results.mode} mode)
            </p>
          </div>

          {/* Empty state */}
          {results.total_results === 0 && !loading && (
            <Card className="p-12 text-center">
              <SearchIcon className="mx-auto h-10 w-10 text-text-tertiary opacity-40 mb-3" />
              <h3 className="text-base font-semibold text-foreground">No matches found</h3>
              <p className="text-xs text-text-secondary mt-1">
                Try refining your keywords or switching to Semantic search mode.
              </p>
            </Card>
          )}

          {/* Meetings List */}
          {(activeTab === "all" || activeTab === "meetings") && results.meetings.length > 0 && (
            <div className="space-y-3">
              {activeTab === "all" && (
                <h3 className="text-xs font-bold uppercase tracking-wider text-text-tertiary">Meetings</h3>
              )}
              {results.meetings.map((m: GlobalSearchMeetingResult) => (
                <Card key={m.id} className="p-4 transition hover:border-accent/50 hover:bg-surface-2/40">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <Link href={`/meetings/${m.id}`} className="font-semibold text-foreground hover:text-accent flex items-center gap-2">
                        <FileText className="h-4 w-4 text-accent" />
                        {m.title}
                      </Link>
                      <p className="text-xs text-text-secondary line-clamp-2">{m.snippet}</p>
                    </div>
                    <Link
                      href={`/meetings/${m.id}`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline shrink-0"
                    >
                      View <ArrowRight className="h-3.3 w-3.3" />
                    </Link>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {/* Action Items List */}
          {(activeTab === "all" || activeTab === "action_items") && results.action_items.length > 0 && (
            <div className="space-y-3">
              {activeTab === "all" && (
                <h3 className="text-xs font-bold uppercase tracking-wider text-text-tertiary mt-6">Action Items</h3>
              )}
              {results.action_items.map((a: GlobalSearchActionResult) => (
                <Card key={a.id} className="p-4 transition hover:border-accent/50 hover:bg-surface-2/40">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                        {a.description}
                      </div>
                      <div className="flex items-center gap-4 text-xs text-text-tertiary pt-1">
                        <span className="flex items-center gap-1">
                          <User className="h-3 w-3" /> {a.owner || "Unassigned"}
                        </span>
                        {a.due_date && (
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" /> Due: {a.due_date}
                          </span>
                        )}
                        <span className="capitalize rounded-md bg-surface-2 px-2 py-0.5 text-[10px] font-semibold text-text-secondary border border-border">
                          {a.status}
                        </span>
                      </div>
                    </div>
                    <Link
                      href={`/meetings/${a.meeting_id}`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline shrink-0"
                    >
                      Open Meeting <ArrowRight className="h-3.3 w-3.3" />
                    </Link>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {/* Decisions List */}
          {(activeTab === "all" || activeTab === "decisions") && results.decisions.length > 0 && (
            <div className="space-y-3">
              {activeTab === "all" && (
                <h3 className="text-xs font-bold uppercase tracking-wider text-text-tertiary mt-6">Decisions</h3>
              )}
              {results.decisions.map((d: GlobalSearchDecisionResult) => (
                <Card key={d.id} className="p-4 transition hover:border-accent/50 hover:bg-surface-2/40">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <HelpCircle className="h-4 w-4 text-purple-400 shrink-0" />
                        {d.description}
                      </div>
                      {d.context && (
                        <p className="text-xs text-text-secondary line-clamp-2 pl-6">{d.context}</p>
                      )}
                    </div>
                    <Link
                      href={`/meetings/${d.meeting_id}`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline shrink-0"
                    >
                      Open Meeting <ArrowRight className="h-3.3 w-3.3" />
                    </Link>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center p-12 text-sm text-text-tertiary"><Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading search...</div>}>
      <SearchContent />
    </Suspense>
  );
}
