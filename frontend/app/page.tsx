"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { useTheme } from "@/components/providers/theme-provider";
import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  Bot,
  Calendar,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  Download,
  FileText,
  Layers,
  Mic,
  Moon,
  Play,
  Search,
  Send,
  Shield,
  Sparkles,
  Sun,
  Terminal,
  Users,
  Zap,
  Check,
  AlertTriangle,
  Radio,
} from "lucide-react";

export default function HomePage() {
  const { user } = useAuth();
  const { theme, toggleTheme, mounted } = useTheme();
  const [activeTab, setActiveTab] = useState<"recorder" | "pdf" | "rag" | "reminders">("recorder");
  const [activeStep, setActiveStep] = useState<number>(2);

  return (
    <div className="min-h-screen bg-background text-foreground transition-colors duration-200">
      {/* =====================================================================
          1. NAVIGATION HEADER
      ====================================================================== */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-foreground text-background">
              <Terminal className="h-5 w-5" />
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold tracking-tight text-foreground">
                  Meeting Intelligence
                </span>
                <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-accent uppercase">
                  Agent v2.0
                </span>
              </div>
            </div>
          </div>

          <nav className="hidden items-center gap-6 text-xs font-medium text-text-secondary md:flex">
            <a href="#problem" className="transition-colors hover:text-foreground">
              Problem
            </a>
            <a href="#solution" className="transition-colors hover:text-foreground">
              Solution
            </a>
            <a href="#why-different" className="transition-colors hover:text-foreground">
              Why Different
            </a>
            <a href="#use-cases" className="transition-colors hover:text-foreground">
              Use Cases
            </a>
            <a href="#interactive-preview" className="transition-colors hover:text-foreground">
              Live Preview
            </a>
          </nav>

          <div className="flex items-center gap-3">
            <button
              onClick={toggleTheme}
              aria-label="Toggle theme"
              className="flex h-8 w-8 items-center justify-center rounded-md border border-border bg-surface text-text-secondary transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              {mounted && theme === "dark" ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
            </button>

            {user ? (
              <Link
                href="/dashboard"
                className="flex h-8 items-center gap-1.5 rounded-md bg-foreground px-3 font-mono text-xs font-medium text-background transition-opacity hover:opacity-90"
              >
                <span>Open Workspace</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  href="/login"
                  className="flex h-8 items-center rounded-md border border-border bg-surface px-3 font-mono text-xs font-medium text-foreground transition-colors hover:bg-surface-2"
                >
                  Sign In
                </Link>
                <Link
                  href="/register"
                  className="flex h-8 items-center gap-1.5 rounded-md bg-foreground px-3 font-mono text-xs font-medium text-background transition-opacity hover:opacity-90"
                >
                  <span>Get Started</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* =====================================================================
          2. HERO SECTION
      ====================================================================== */}
      <section className="relative overflow-hidden pt-12 pb-20 md:pt-20 md:pb-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid items-center gap-12 lg:grid-cols-12">
            {/* Left Column: Headline and CTAs */}
            <div className="lg:col-span-6 space-y-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 font-mono text-[11px] text-text-secondary">
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>STATE_MACHINE: 7-NODE ORCHESTRATION</span>
              </div>

              <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl">
                Stop losing decisions in{" "}
                <span className="bg-gradient-to-r from-accent to-amber-500 bg-clip-text text-transparent">
                  meeting recordings.
                </span>
              </h1>

              <p className="max-w-xl text-base leading-relaxed text-text-secondary sm:text-lg">
                An autonomous agentic intelligence platform that listens, diarizes speakers,
                extracts structured deliverables, and automates your entire post-meeting
                workflow with zero manual note-taking.
              </p>

              <div className="flex flex-wrap items-center gap-3 pt-2">
                {user ? (
                  <Link
                    href="/dashboard"
                    className="flex h-11 items-center gap-2 rounded-lg bg-foreground px-5 font-mono text-sm font-semibold text-background transition-opacity hover:opacity-90"
                  >
                    <span>Launch Dashboard</span>
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                ) : (
                  <>
                    <Link
                      href="/register"
                      className="flex h-11 items-center gap-2 rounded-lg bg-foreground px-5 font-mono text-sm font-semibold text-background transition-opacity hover:opacity-90"
                    >
                      <span>Get Started Free</span>
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                    <Link
                      href="/login"
                      className="flex h-11 items-center rounded-lg border border-border bg-surface px-5 font-mono text-sm font-semibold text-foreground transition-colors hover:bg-surface-2"
                    >
                      Sign In to Workspace
                    </Link>
                  </>
                )}
              </div>

              <div className="grid grid-cols-3 gap-4 pt-6 border-t border-border">
                <div>
                  <p className="font-mono text-xl font-bold text-foreground sm:text-2xl">100%</p>
                  <p className="text-xs text-text-tertiary">Verbatim Context</p>
                </div>
                <div>
                  <p className="font-mono text-xl font-bold text-foreground sm:text-2xl">&lt; 30s</p>
                  <p className="text-xs text-text-tertiary">Whisper Ingestion</p>
                </div>
                <div>
                  <p className="font-mono text-xl font-bold text-foreground sm:text-2xl">4 Tools</p>
                  <p className="text-xs text-text-tertiary">Jira, Slack, Cal, Email</p>
                </div>
              </div>
            </div>

            {/* Right Column: Claude-Code-Style Simulated Terminal */}
            <div className="lg:col-span-6">
              <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
                {/* Terminal Header */}
                <div className="flex items-center justify-between border-b border-border bg-surface-2 px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full bg-red-500/80" />
                    <div className="h-3 w-3 rounded-full bg-amber-500/80" />
                    <div className="h-3 w-3 rounded-full bg-emerald-500/80" />
                    <span className="ml-2 font-mono text-xs text-text-tertiary">
                      agent-graph-orchestrator.sh
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-accent">LIVE_INFERENCE</span>
                </div>

                {/* Terminal Body */}
                <div className="space-y-4 p-5 font-mono text-xs">
                  <div className="flex items-start justify-between border-b border-border/50 pb-3">
                    <div className="space-y-1">
                      <p className="text-text-tertiary">$ agent run --file "q4-product-sync.mp4"</p>
                      <p className="text-foreground">Processing 42m 18s audio payload (73.4 MB)...</p>
                    </div>
                    <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-500">
                      SUCCESS
                    </span>
                  </div>

                  {/* Step Selector Buttons */}
                  <div className="grid grid-cols-4 gap-1.5">
                    {[
                      { id: 1, label: "01_INGEST" },
                      { id: 2, label: "02_DIARIZE" },
                      { id: 3, label: "03_EXTRACT" },
                      { id: 4, label: "04_DISPATCH" },
                    ].map((step) => (
                      <button
                        key={step.id}
                        onClick={() => setActiveStep(step.id)}
                        className={`rounded px-2 py-1 text-[10px] font-semibold transition-colors ${
                          activeStep === step.id
                            ? "bg-foreground text-background"
                            : "bg-surface-2 text-text-tertiary hover:text-foreground"
                        }`}
                      >
                        {step.label}
                      </button>
                    ))}
                  </div>

                  {/* Step Dynamic Content */}
                  <div className="rounded-lg border border-border/80 bg-surface-2 p-3 text-[11px] leading-relaxed">
                    {activeStep === 1 && (
                      <div className="space-y-1.5 text-text-secondary">
                        <p className="text-accent font-semibold">[NODE 1] Audio Validation & Chunking</p>
                        <p>• File format: MP4 container with AAC audio stream</p>
                        <p>• Size &gt; 25MB: Segmented into 5 lossless chunks via ffmpeg</p>
                        <p>• Speech transcription: Groq Whisper Llama-3 API in 2.8s</p>
                      </div>
                    )}
                    {activeStep === 2 && (
                      <div className="space-y-1.5 text-text-secondary">
                        <p className="text-accent font-semibold">[NODE 2] Acoustic Diarization</p>
                        <p>• SPEAKER_00 [00:02 - 14:10] → Resolved to: Alice Chen (Lead)</p>
                        <p>• SPEAKER_01 [14:12 - 28:40] → Resolved to: Bob Smith (Eng)</p>
                        <p>• Transcript updated with speaker turn attribution</p>
                      </div>
                    )}
                    {activeStep === 3 && (
                      <div className="space-y-1.5 text-text-secondary">
                        <p className="text-accent font-semibold">[NODE 3] Entity Extraction & RAG Vector</p>
                        <p>• Action items: 4 tasks detected with owners, due dates, and priorities</p>
                        <p>• Decisions: 2 strategic architectural decisions recorded with context</p>
                        <p>• Vector embedding: 768-dim vector indexed in Neon pgvector</p>
                      </div>
                    )}
                    {activeStep === 4 && (
                      <div className="space-y-1.5 text-text-secondary">
                        <p className="text-accent font-semibold">[NODE 4] Multi-Tool Synchronization</p>
                        <p>• Jira: Issue SRUM-42 created for Bob Smith</p>
                        <p>• Slack: Formatted Block Kit brief posted to #product-sync</p>
                        <p>• Reminders: Scheduled automated due-date cron alert for 2026-09-25</p>
                      </div>
                    )}
                  </div>

                  {/* Terminal Footer Indicator */}
                  <div className="flex items-center justify-between text-[10px] text-text-tertiary">
                    <span className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      State: GraphExecutionComplete
                    </span>
                    <span>Neon pgvector: synchronized</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          3. SECTION: THE PROBLEM
      ====================================================================== */}
      <section id="problem" className="border-t border-border py-16 sm:py-20 bg-surface/30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-12">
          <div className="space-y-3">
            <p className="font-mono text-xs uppercase tracking-widest text-accent">
              [ THE PROBLEM ]
            </p>
            <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Meetings are black holes where decisions quietly die.
            </h2>
            <p className="max-w-2xl text-sm text-text-secondary">
              High-value teams spend over 40% of their work week in strategic discussions,
              yet the knowledge generated is immediately lost to poor retention and manual friction.
            </p>
          </div>

          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {/* Problem Card 1 */}
            <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10 text-red-500 border border-red-500/20">
                <Clock className="h-5 w-5" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">The 60-Minute Black Hole</h3>
              <p className="text-sm leading-relaxed text-text-secondary">
                Recorded audio files sit in cloud drives where no one has the time to re-listen.
                Crucial debates and context vanish the moment the call ends.
              </p>
              <div className="pt-2">
                <span className="font-mono text-xs text-red-400 bg-red-500/10 px-2 py-0.5 rounded">
                  Status: 92% of recordings never reopened
                </span>
              </div>
            </div>

            {/* Problem Card 2 */}
            <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10 text-amber-500 border border-amber-500/20">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">Lost Commitments & Due Dates</h3>
              <p className="text-sm leading-relaxed text-text-secondary">
                Action items agreed verbally are forgotten by the next morning. Deadlines slip
                because no one transcribed the task into Jira or assigned clear ownership.
              </p>
              <div className="pt-2">
                <span className="font-mono text-xs text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded">
                  Status: Zero accountability
                </span>
              </div>
            </div>

            {/* Problem Card 3 */}
            <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/10 text-purple-500 border border-purple-500/20">
                <FileText className="h-5 w-5" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">Manual Post-Meeting Busywork</h3>
              <p className="text-sm leading-relaxed text-text-secondary">
                Product managers and team leads waste 45 minutes after every session manually writing
                meeting minutes, filing tickets, and crafting update emails.
              </p>
              <div className="pt-2">
                <span className="font-mono text-xs text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded">
                  Status: 5+ hours lost per week
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          4. SECTION: OUR SOLUTION
      ====================================================================== */}
      <section id="solution" className="border-t border-border py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-12">
          <div className="space-y-3">
            <p className="font-mono text-xs uppercase tracking-widest text-accent">
              [ OUR SOLUTION ]
            </p>
            <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              An autonomous agentic workflow that executes for you.
            </h2>
            <p className="max-w-2xl text-sm text-text-secondary">
              A comprehensive state machine that transforms audio into verifiable deliverables,
              searchable vectors, and workplace integrations.
            </p>
          </div>

          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {/* Feature 1 */}
            <div className="group rounded-xl border border-border bg-surface p-6 space-y-3 transition-all hover:border-accent/40">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-foreground group-hover:text-accent">
                <Mic className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-foreground">Live Browser Voice Recording</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Record meetings live using the MediaRecorder API with real-time waveform visualization,
                timer controls, and in-browser playback preview.
              </p>
              <span className="font-mono text-[10px] text-text-tertiary">
                Web Audio API • AnalyserNode
              </span>
            </div>

            {/* Feature 2 */}
            <div className="group rounded-xl border border-border bg-surface p-6 space-y-3 transition-all hover:border-accent/40">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-foreground group-hover:text-accent">
                <Users className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-foreground">Speaker Diarization</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Acoustic voiceprint analysis attributes every spoken turn to distinct speaker
                labels with interactive mapping to real team member identities.
              </p>
              <span className="font-mono text-[10px] text-text-tertiary">
                PyAnnote • Timestamp Alignment
              </span>
            </div>

            {/* Feature 3 */}
            <div className="group rounded-xl border border-border bg-surface p-6 space-y-3 transition-all hover:border-accent/40">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-foreground group-hover:text-accent">
                <CheckCircle2 className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-foreground">Structured Entity Extraction</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Parses conversation into typed action items with designated owners, ISO due dates,
                priority rankings, and formal decision logs with context.
              </p>
              <span className="font-mono text-[10px] text-text-tertiary">
                Pydantic Validation • Typed Schemas
              </span>
            </div>

            {/* Feature 4 */}
            <div className="group rounded-xl border border-border bg-surface p-6 space-y-3 transition-all hover:border-accent/40">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-foreground group-hover:text-accent">
                <Download className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-foreground">One-Click Vector PDF Export</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Generates executive-ready PDF documents with two-pass pagination ("Page X of Y"),
                running footers, color-coded deliverables, and decision logs.
              </p>
              <span className="font-mono text-[10px] text-text-tertiary">
                ReportLab • Vector Typography
              </span>
            </div>

            {/* Feature 5 */}
            <div className="group rounded-xl border border-border bg-surface p-6 space-y-3 transition-all hover:border-accent/40">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-foreground group-hover:text-accent">
                <Bot className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-foreground">Conversational RAG Agent</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Query single meetings or your entire historical repository via real-time SSE streaming
                grounded in 60,000+ characters of verbatim transcripts.
              </p>
              <span className="font-mono text-[10px] text-text-tertiary">
                pgvector • Multi-Turn Memory
              </span>
            </div>

            {/* Feature 6 */}
            <div className="group rounded-xl border border-border bg-surface p-6 space-y-3 transition-all hover:border-accent/40">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-foreground group-hover:text-accent">
                <Bell className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-foreground">Due-Date Reminders & Dispatch</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Background cron checks deadlines hourly and dispatches automated reminder emails
                and Slack alerts, with one-click dispatch to Jira and Calendar.
              </p>
              <span className="font-mono text-[10px] text-text-tertiary">
                SendGrid • Slack Block Kit • Jira API
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          5. SECTION: WHY THIS IS DIFFERENT
      ====================================================================== */}
      <section id="why-different" className="border-t border-border py-16 sm:py-20 bg-surface/30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-12">
          <div className="space-y-3">
            <p className="font-mono text-xs uppercase tracking-widest text-accent">
              [ WHY IT&apos;S DIFFERENT ]
            </p>
            <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Engineered like developer tooling, not a toy note-taker.
            </h2>
            <p className="max-w-2xl text-sm text-text-secondary">
              Most AI meeting tools are simple wrappers around basic speech APIs that truncate context.
              We built an observable, resilient multi-agent architecture.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            {/* Difference 1 */}
            <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-semibold text-accent">[ ARCHITECTURE ]</span>
                <span className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-500">
                  LANGGRAPH v0.2
                </span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                Stateful Agent Graph vs Single Prompt Chains
              </h3>
              <p className="text-sm text-text-secondary leading-relaxed">
                Rather than attempting to extract everything in one lossy LLM call, our pipeline
                executes as a directed acyclic graph where each node specializes in validation,
                transcription, extraction, synthesis, or vectorization with automatic retry policies.
              </p>
              <div className="rounded-lg bg-surface-2 p-3 font-mono text-xs text-text-secondary">
                Validation → Segmentation → Diarization → Whisper → Extraction → Vectorization
              </div>
            </div>

            {/* Difference 2 */}
            <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-semibold text-accent">[ INGESTION ]</span>
                <span className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-500">
                  NO SIZE LIMITS
                </span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                Adaptive Audio Chunking vs File Rejections
              </h3>
              <p className="text-sm text-text-secondary leading-relaxed">
                Standard speech APIs crash when an audio file exceeds 25 MB. Our ingestion agent
                automatically detects large recordings and segments them into lossless 10-minute
                chunks via stream-copy muxing, merging transcripts seamlessly without quality degradation.
              </p>
              <div className="rounded-lg bg-surface-2 p-3 font-mono text-xs text-text-secondary">
                Stream-copy muxing • Zero re-encoding latency • Handles 2hr+ recordings
              </div>
            </div>

            {/* Difference 3 */}
            <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-semibold text-accent">[ GOVERNANCE ]</span>
                <span className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-500">
                  HUMAN-IN-THE-LOOP
                </span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                Granular Review Before External Dispatch
              </h3>
              <p className="text-sm text-text-secondary leading-relaxed">
                Uncontrolled bots spamming Jira or Slack with hallucinations destroy trust.
                Meeting Intelligence Agent enforces a governance gate where organizers can review,
                edit owners, adjust deadlines, and selectively approve channel dispatches.
              </p>
              <div className="rounded-lg bg-surface-2 p-3 font-mono text-xs text-text-secondary">
                Editable owners • Due date adjustment • Selective channel triggers
              </div>
            </div>

            {/* Difference 4 */}
            <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-semibold text-accent">[ INTEGRATION ]</span>
                <span className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-500">
                  PER-USER CREDS
                </span>
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                Personalized Tool Credentials vs Shared Env Defaults
              </h3>
              <p className="text-sm text-text-secondary leading-relaxed">
                Every team member can configure their own personal Jira, Slack, SendGrid, and
                Calendar credentials directly in the UI. Action items and tickets are created
                under your personal account rather than an impersonal shared bot identity.
              </p>
              <div className="rounded-lg bg-surface-2 p-3 font-mono text-xs text-text-secondary">
                User-level encryption • Live connection tests • System fallback
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          6. SECTION: WHAT IT'S MOSTLY USED FOR (CORE USE CASES)
      ====================================================================== */}
      <section id="use-cases" className="border-t border-border py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-12">
          <div className="space-y-3">
            <p className="font-mono text-xs uppercase tracking-widest text-accent">
              [ CORE USE CASES ]
            </p>
            <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Where teams deploy Meeting Intelligence Agent.
            </h2>
            <p className="max-w-2xl text-sm text-text-secondary">
              Designed for software engineering teams, leadership syncs, and client-facing operations.
            </p>
          </div>

          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {/* Use Case 1 */}
            <div className="rounded-xl border border-border bg-surface p-5 space-y-3">
              <div className="flex h-8 w-8 items-center justify-center rounded bg-blue-500/10 text-blue-500">
                <Cpu className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">Sprint Planning & Standups</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Turn 45-minute sprint planning meetings into instantly formatted Jira issues,
                dispatched straight into your backlog with assigned owners.
              </p>
            </div>

            {/* Use Case 2 */}
            <div className="rounded-xl border border-border bg-surface p-5 space-y-3">
              <div className="flex h-8 w-8 items-center justify-center rounded bg-purple-500/10 text-purple-500">
                <FileText className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">Executive & Board Syncs</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Generate polished vector PDF summaries with formal key decisions logs and high-level
                takeaways for stakeholders and board members.
              </p>
            </div>

            {/* Use Case 3 */}
            <div className="rounded-xl border border-border bg-surface p-5 space-y-3">
              <div className="flex h-8 w-8 items-center justify-center rounded bg-amber-500/10 text-amber-500">
                <Bell className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">Client Discovery & Sales</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Track client requirements and commitments with automated due-date reminder emails
                so no deliverable is missed before the next call.
              </p>
            </div>

            {/* Use Case 4 */}
            <div className="rounded-xl border border-border bg-surface p-5 space-y-3">
              <div className="flex h-8 w-8 items-center justify-center rounded bg-emerald-500/10 text-emerald-500">
                <Search className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">Cross-Meeting Knowledge Discovery</h3>
              <p className="text-xs leading-relaxed text-text-secondary">
                Ask questions like "What did we decide about database auth three weeks ago?" and
                receive exact cited answers grounded in full transcripts.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          7. SECTION: INTERACTIVE FEATURE PREVIEWS
      ====================================================================== */}
      <section id="interactive-preview" className="border-t border-border py-16 sm:py-20 bg-surface/30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="font-mono text-xs uppercase tracking-widest text-accent">
                [ INTERACTIVE SHOWCASE ]
              </p>
              <h2 className="mt-1 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                Experience the core capabilities.
              </h2>
            </div>

            {/* Tab selector */}
            <div className="flex flex-wrap gap-1 rounded-lg border border-border bg-surface p-1">
              {[
                { id: "recorder", label: "Voice Recorder", icon: Mic },
                { id: "pdf", label: "PDF Export", icon: Download },
                { id: "rag", label: "Agent Chat RAG", icon: Bot },
                { id: "reminders", label: "Due Reminders", icon: Bell },
              ].map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as typeof activeTab)}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 font-mono text-xs font-medium transition-colors ${
                      activeTab === tab.id
                        ? "bg-foreground text-background"
                        : "text-text-secondary hover:text-foreground"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tab Showcase Card */}
          <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
            {activeTab === "recorder" && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border pb-4">
                  <div>
                    <h3 className="text-base font-semibold text-foreground">
                      In-Browser Live Audio Recording
                    </h3>
                    <p className="text-xs text-text-secondary">
                      Capture high-fidelity meeting audio directly from your browser with real-time waveform visualization.
                    </p>
                  </div>
                  <span className="flex items-center gap-1.5 rounded-full bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-500 border border-red-500/20">
                    <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                    REC 04:18
                  </span>
                </div>

                {/* Simulated Audio Waveform */}
                <div className="flex h-24 items-center justify-center gap-1 rounded-lg bg-surface-2 px-4">
                  {[24, 45, 60, 30, 80, 95, 40, 70, 85, 30, 90, 100, 65, 45, 80, 55, 35, 75, 90, 60, 40, 85, 70, 50].map(
                    (height, idx) => (
                      <div
                        key={idx}
                        className="w-1.5 rounded-full bg-accent transition-all duration-150"
                        style={{ height: `${height}%` }}
                      />
                    )
                  )}
                </div>

                <div className="flex items-center justify-between text-xs text-text-secondary font-mono">
                  <span>Format: audio/webm;codecs=opus</span>
                  <span>Bitrate: 128 kbps (Lossless chunking enabled)</span>
                </div>
              </div>
            )}

            {activeTab === "pdf" && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border pb-4">
                  <div>
                    <h3 className="text-base font-semibold text-foreground">
                      One-Click Executive PDF Document
                    </h3>
                    <p className="text-xs text-text-secondary">
                      Compiled server-side using ReportLab vector typography with running footers and color-coded deliverables.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-text-tertiary">PDF 2.0 Vector</span>
                    <span className="rounded bg-accent/10 px-2 py-0.5 font-mono text-xs font-semibold text-accent">
                      Two-Pass
                    </span>
                  </div>
                </div>

                <div className="rounded-lg border border-border bg-surface-2 p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-border pb-3">
                    <div>
                      <p className="font-mono text-[10px] uppercase text-accent font-semibold">
                        MEETING INTELLIGENCE REPORT
                      </p>
                      <h4 className="text-sm font-bold text-foreground">
                        Q4 Strategic Roadmap & Architecture Sync
                      </h4>
                    </div>
                    <span className="font-mono text-xs text-text-tertiary">Page 1 of 3</span>
                  </div>

                  <div className="space-y-2 text-xs">
                    <p className="font-semibold text-foreground">Executive Summary</p>
                    <p className="text-text-secondary leading-relaxed">
                      The engineering team approved the transition to LangGraph state orchestration
                      and Neon pgvector embeddings. Action items were assigned to complete credential
                      migration by September 25.
                    </p>
                  </div>

                  <div className="grid grid-cols-3 gap-2 pt-2 border-t border-border/60 text-xs">
                    <div>
                      <span className="text-text-tertiary">Task:</span>{" "}
                      <span className="font-medium text-foreground">Migrate Auth</span>
                    </div>
                    <div>
                      <span className="text-text-tertiary">Owner:</span>{" "}
                      <span className="font-medium text-foreground">Alice Chen</span>
                    </div>
                    <div>
                      <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-red-500">
                        High Priority
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "rag" && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border pb-4">
                  <div>
                    <h3 className="text-base font-semibold text-foreground">
                      Streaming Conversational RAG
                    </h3>
                    <p className="text-xs text-text-secondary">
                      Answers complex inquiries backed by verbatim diarized transcripts and multi-turn conversational memory.
                    </p>
                  </div>
                  <span className="font-mono text-xs text-emerald-500 flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    SSE_STREAMING
                  </span>
                </div>

                <div className="space-y-3 font-mono text-xs">
                  <div className="flex items-start gap-2 text-text-secondary">
                    <span className="font-bold text-foreground">&gt; User:</span>
                    <p className="text-foreground">
                      What did we decide about the Groq Whisper transcription timeout?
                    </p>
                  </div>

                  <div className="rounded-lg border border-border bg-surface-2 p-3 space-y-2">
                    <div className="flex items-center gap-2 text-accent">
                      <Bot className="h-3.5 w-3.5" />
                      <span className="font-semibold">Intelligence Agent</span>
                      <span className="text-[10px] text-text-tertiary">[Citations: Meeting #104, #108]</span>
                    </div>
                    <p className="text-text-secondary leading-relaxed">
                      During the September 14 sync, Bob Smith confirmed that Groq Whisper requests
                      are capped at 24 MB. For recordings longer than 10 minutes, the pipeline invokes
                      stream-copy segmentation with a 120-second timeout per chunk.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "reminders" && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border pb-4">
                  <div>
                    <h3 className="text-base font-semibold text-foreground">
                      Automated Action Item Due-Date Reminders
                    </h3>
                    <p className="text-xs text-text-secondary">
                      Background scheduler tracks task deadlines and dispatches email and Slack reminders with anti-spam deduplication.
                    </p>
                  </div>
                  <span className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-xs font-semibold text-emerald-500">
                    Cron: Hourly Check
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between rounded-lg border border-border bg-surface-2 p-3 text-xs">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground">
                          Complete security audit for tool credentials
                        </span>
                        <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-semibold text-red-500 border border-red-500/20">
                          Overdue (2026-09-18)
                        </span>
                      </div>
                      <p className="text-text-tertiary">Assignee: Alice Chen • Priority: High</p>
                    </div>
                    <span className="font-mono text-[11px] text-text-secondary">Email Sent</span>
                  </div>

                  <div className="flex items-center justify-between rounded-lg border border-border bg-surface-2 p-3 text-xs">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground">
                          Verify SendGrid transactional templates
                        </span>
                        <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-500 border border-amber-500/20">
                          Due Today
                        </span>
                      </div>
                      <p className="text-text-tertiary">Assignee: Bob Smith • Priority: Medium</p>
                    </div>
                    <span className="font-mono text-[11px] text-text-secondary">Slack Queued</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* =====================================================================
          8. SECTION: BOTTOM CTA BANNER
      ====================================================================== */}
      <section className="border-t border-border py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-b from-surface to-surface-2 p-8 text-center sm:p-12 lg:p-16 space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 font-mono text-xs text-text-secondary">
              <span>ENTERPRISE AGENTIC WORKSPACE</span>
            </div>

            <h2 className="mx-auto max-w-2xl text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Turn your next meeting into immediate execution.
            </h2>

            <p className="mx-auto max-w-xl text-sm leading-relaxed text-text-secondary sm:text-base">
              Start recording or upload any audio file in seconds. No credit card required.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
              {user ? (
                <Link
                  href="/dashboard"
                  className="flex h-11 items-center gap-2 rounded-lg bg-foreground px-6 font-mono text-sm font-semibold text-background transition-opacity hover:opacity-90"
                >
                  <span>Go to Dashboard</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              ) : (
                <>
                  <Link
                    href="/register"
                    className="flex h-11 items-center gap-2 rounded-lg bg-foreground px-6 font-mono text-sm font-semibold text-background transition-opacity hover:opacity-90"
                  >
                    <span>Create Free Account</span>
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                  <Link
                    href="/login"
                    className="flex h-11 items-center rounded-lg border border-border bg-surface px-6 font-mono text-sm font-semibold text-foreground transition-colors hover:bg-surface-2"
                  >
                    Sign In to Existing Account
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          9. FOOTER
      ====================================================================== */}
      <footer className="border-t border-border py-8 text-xs text-text-tertiary">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 sm:flex-row sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground">Meeting Intelligence Agent</span>
            <span>•</span>
            <span>v2.0 Enterprise</span>
          </div>

          <div className="flex items-center gap-4 font-mono text-[11px]">
            <span>FastAPI</span>
            <span>•</span>
            <span>LangGraph</span>
            <span>•</span>
            <span>Groq Whisper</span>
            <span>•</span>
            <span>Neon pgvector</span>
            <span>•</span>
            <span>Next.js 16</span>
          </div>

          <p>© {new Date().getFullYear()} Meeting Intelligence Agent. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
