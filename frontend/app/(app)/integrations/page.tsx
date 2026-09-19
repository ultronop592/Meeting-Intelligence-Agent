"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircle,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Eye,
  EyeOff,
  Info,
  Loader2,
  Mail,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  Ticket,
  Trash2,
} from "lucide-react";
import { integrationsApi } from "@/lib/api/meetings";
import type {
  ToolName,
  ToolStatusResponse,
  TestConnectionResponse,
} from "@/types/api";

export default function IntegrationsPage() {
  const queryClient = useQueryClient();

  const {
    data: integrations,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["integrations"],
    queryFn: () => integrationsApi.getIntegrations(),
  });

  const [expandedCards, setExpandedCards] = useState<Record<ToolName, boolean>>({
    jira: false,
    slack: false,
    email: false,
    calendar: false,
  });

  // Form states
  const [jiraForm, setJiraForm] = useState({
    url: "",
    email: "",
    api_token: "",
    project_key: "",
  });
  const [showJiraToken, setShowJiraToken] = useState(false);

  const [slackForm, setSlackForm] = useState({
    webhook_url: "",
    channel: "",
  });

  const [emailForm, setEmailForm] = useState({
    api_key: "",
    sender_email: "",
    sender_name: "",
  });
  const [showEmailKey, setShowEmailKey] = useState(false);

  const [calendarForm, setCalendarForm] = useState({
    calendar_id: "",
    credentials_json: "",
  });

  // Connection testing states
  const [testingTool, setTestingTool] = useState<ToolName | null>(null);
  const [testResults, setTestResults] = useState<
    Record<string, TestConnectionResponse | null>
  >({});

  const toggleExpand = (tool: ToolName) => {
    setExpandedCards((prev) => {
      const nextState = !prev[tool];
      if (nextState && integrations && integrations[tool]) {
        const d = integrations[tool].details;
        if (tool === "jira") {
          setJiraForm({
            url: d.url || "",
            email: d.email || "",
            api_token: "",
            project_key: d.project_key || "",
          });
        } else if (tool === "slack") {
          setSlackForm({
            webhook_url: "",
            channel: d.channel || "#general",
          });
        } else if (tool === "email") {
          setEmailForm({
            api_key: "",
            sender_email: d.sender_email || "",
            sender_name: d.sender_name || "Meeting Intelligence Agent",
          });
        } else if (tool === "calendar") {
          setCalendarForm({
            calendar_id: d.calendar_id || "",
            credentials_json: "",
          });
        }
      }
      return { ...prev, [tool]: nextState };
    });
  };

  const updateMutation = useMutation({
    mutationFn: ({
      tool,
      payload,
    }: {
      tool: ToolName;
      payload: Record<string, unknown>;
    }) => integrationsApi.updateIntegration(tool, payload),
    onSuccess: (data, variables) => {
      toast.success(
        data.message ||
          `${variables.tool.toUpperCase()} credentials saved successfully.`
      );
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      setExpandedCards((prev) => ({ ...prev, [variables.tool]: false }));
      setTestResults((prev) => ({ ...prev, [variables.tool]: null }));
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to save credentials.";
      toast.error(msg);
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: (tool: ToolName) => integrationsApi.disconnectIntegration(tool),
    onSuccess: (data, tool) => {
      toast.success(
        data.message || `${tool.toUpperCase()} disconnected successfully.`
      );
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      setTestResults((prev) => ({ ...prev, [tool]: null }));
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to disconnect.";
      toast.error(msg);
    },
  });

  const handleTestConnection = async (
    tool: ToolName,
    payload?: Record<string, unknown>
  ) => {
    setTestingTool(tool);
    try {
      const res = await integrationsApi.testConnection(tool, payload);
      setTestResults((prev) => ({ ...prev, [tool]: res }));
      if (res.success) {
        toast.success(res.message);
      } else {
        toast.error(res.message, { description: res.error || undefined });
      }
    } catch (err: unknown) {
      const errorMsg =
        err instanceof Error ? err.message : "Network error testing connection.";
      const errorRes: TestConnectionResponse = {
        success: false,
        message: `Failed to test ${tool} connection`,
        error: errorMsg,
      };
      setTestResults((prev) => ({ ...prev, [tool]: errorRes }));
      toast.error(errorRes.message, { description: errorRes.error || undefined });
    } finally {
      setTestingTool(null);
    }
  };

  const getStatusBadge = (status?: ToolStatusResponse) => {
    if (!status || !status.connected) {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-2 px-2.5 py-0.5 text-[11px] font-medium text-text-tertiary">
          <span className="h-1.5 w-1.5 rounded-full bg-text-tertiary/60" />
          Not Connected
        </span>
      );
    }
    if (status.is_custom) {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-medium text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          Connected (Personal)
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-0.5 text-[11px] font-medium text-sky-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
        Connected (System Default)
      </span>
    );
  };

  const totalConnected = integrations
    ? Object.values(integrations).filter((t) => t.connected).length
    : 0;

  return (
    <div className="mx-auto max-w-6xl space-y-app-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-text-tertiary">
            Settings & Integrations
          </p>
          <h1 className="heading-title mt-1 text-foreground flex items-center gap-2">
            <SlidersHorizontal className="h-6 w-6 text-accent" />
            External Tool Credentials
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            Connect personal or organization accounts for Jira, Slack, SendGrid, and Google Calendar. Automations run under your credentials.
          </p>
        </div>

        <button
          id="btn-refresh-integrations"
          onClick={() => refetch()}
          disabled={isLoading}
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3.5 py-2 text-xs font-medium text-foreground transition-all hover:bg-surface-2 disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isLoading ? "animate-spin text-accent" : "text-text-tertiary"}`}
          />
          Refresh Status
        </button>
      </div>

      {/* Info & Security Banner */}
      <div className="rounded-2xl border border-border/70 bg-surface p-4 text-xs text-text-secondary shadow-xs">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-accent/10 p-2 text-accent">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div className="flex-1 space-y-1">
            <div className="flex items-center justify-between">
              <p className="font-semibold text-foreground text-sm">
                Tenant Isolation & Secret Protection
              </p>
              <span className="rounded-md border border-border bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-foreground">
                {totalConnected} of 4 Tools Active
              </span>
            </div>
            <p className="leading-relaxed">
              When configured, your personal credentials override system-wide defaults for ticket creation, Slack summaries, personalized emails, and calendar bookings. Secrets are masked before leaving the server and are never exposed in cleartext.
            </p>
          </div>
        </div>
      </div>

      {/* Tools Grid */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {/* ================================================================= */}
        {/* 1. JIRA CARD */}
        {/* ================================================================= */}
        <div
          id="tool-card-jira"
          className="rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all hover:border-border"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400">
                <Ticket className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-foreground">Atlassian Jira</h2>
                <p className="text-xs text-text-secondary">
                  Create action item tickets with owners and due dates
                </p>
              </div>
            </div>
            {getStatusBadge(integrations?.jira)}
          </div>

          {/* Current Details Preview */}
          <div className="mt-4 rounded-xl border border-border/60 bg-surface-2/60 p-3 text-xs space-y-1.5">
            <div className="flex justify-between">
              <span className="text-text-tertiary">Jira URL:</span>
              <span className="font-medium text-foreground">
                {integrations?.jira?.details?.url || "Not configured"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-tertiary">Account Email:</span>
              <span className="font-medium text-foreground">
                {integrations?.jira?.details?.email || "Not configured"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-tertiary">Project Key:</span>
              <span className="font-medium text-foreground">
                {integrations?.jira?.details?.project_key || "Not configured"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-tertiary">API Token:</span>
              <span className="font-mono text-foreground">
                {integrations?.jira?.details?.api_token_masked || "None"}
              </span>
            </div>
          </div>

          {/* Test connection alert banner */}
          {testResults.jira && (
            <div
              className={`mt-3 flex items-start gap-2.5 rounded-xl border p-3 text-xs ${
                testResults.jira.success
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-red-500/30 bg-red-500/10 text-red-300"
              }`}
            >
              {testResults.jira.success ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
              )}
              <div className="flex-1">
                <p className="font-medium">{testResults.jira.message}</p>
                {testResults.jira.error && (
                  <p className="mt-0.5 text-[11px] opacity-90">{testResults.jira.error}</p>
                )}
              </div>
            </div>
          )}

          {/* Action Bar */}
          <div className="mt-4 flex items-center justify-between pt-3 border-t border-border/60">
            <div className="flex items-center gap-2">
              <button
                id="btn-test-jira"
                onClick={() =>
                  handleTestConnection(
                    "jira",
                    expandedCards.jira && jiraForm.url ? jiraForm : undefined
                  )
                }
                disabled={testingTool === "jira"}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-surface-2 disabled:opacity-50"
              >
                {testingTool === "jira" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
                ) : (
                  <Check className="h-3.5 w-3.5 text-text-tertiary" />
                )}
                Test Connection
              </button>

              {integrations?.jira?.is_custom && (
                <button
                  id="btn-disconnect-jira"
                  onClick={() => disconnectMutation.mutate("jira")}
                  disabled={disconnectMutation.isPending}
                  className="inline-flex items-center gap-1 rounded-lg border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-xs text-red-400 hover:bg-red-500/20"
                  title="Disconnect custom credentials and revert to workspace default"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Disconnect
                </button>
              )}
            </div>

            <button
              id="btn-expand-jira"
              onClick={() => toggleExpand("jira")}
              className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              {expandedCards.jira ? (
                <>
                  Close <ChevronUp className="h-3.5 w-3.5" />
                </>
              ) : (
                <>
                  Configure <ChevronDown className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>

          {/* Expanded Configuration Form */}
          {expandedCards.jira && (
            <form
              id="form-jira"
              onSubmit={(e) => {
                e.preventDefault();
                updateMutation.mutate({ tool: "jira", payload: jiraForm });
              }}
              className="mt-4 space-y-3 rounded-xl border border-border bg-surface-2 p-3.5"
            >
              <div>
                <label className="block text-[11px] font-medium text-text-secondary">
                  Jira URL
                </label>
                <input
                  id="input-jira-url"
                  type="url"
                  required
                  placeholder="https://yourcompany.atlassian.net"
                  value={jiraForm.url}
                  onChange={(e) => setJiraForm({ ...jiraForm, url: e.target.value })}
                  className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-text-secondary">
                    Account Email
                  </label>
                  <input
                    id="input-jira-email"
                    type="email"
                    required
                    placeholder="user@company.com"
                    value={jiraForm.email}
                    onChange={(e) => setJiraForm({ ...jiraForm, email: e.target.value })}
                    className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-text-secondary">
                    Project Key
                  </label>
                  <input
                    id="input-jira-project"
                    type="text"
                    required
                    placeholder="PROJ"
                    value={jiraForm.project_key}
                    onChange={(e) =>
                      setJiraForm({ ...jiraForm, project_key: e.target.value.toUpperCase() })
                    }
                    className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-[11px] font-medium text-text-secondary">
                    API Token
                  </label>
                  <a
                    href="https://id.atlassian.com/manage-profile/security/api-tokens"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[10px] text-accent hover:underline"
                  >
                    Generate Token <ExternalLink className="h-2.5 w-2.5" />
                  </a>
                </div>
                <div className="relative mt-1">
                  <input
                    id="input-jira-token"
                    type={showJiraToken ? "text" : "password"}
                    placeholder={
                      integrations?.jira?.details?.has_api_token
                        ? "Leave blank to keep existing token"
                        : "Paste Jira API token"
                    }
                    value={jiraForm.api_token}
                    onChange={(e) =>
                      setJiraForm({ ...jiraForm, api_token: e.target.value })
                    }
                    className="w-full rounded-lg border border-border bg-surface px-3 py-1.5 pr-8 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                  />
                  <button
                    type="button"
                    onClick={() => setShowJiraToken(!showJiraToken)}
                    className="absolute right-2.5 top-2 text-text-tertiary hover:text-foreground"
                  >
                    {showJiraToken ? (
                      <EyeOff className="h-3.5 w-3.5" />
                    ) : (
                      <Eye className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  id="btn-save-jira"
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="rounded-lg bg-accent px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:opacity-90 disabled:opacity-50"
                >
                  {updateMutation.isPending ? "Saving..." : "Save Jira Credentials"}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* ================================================================= */}
        {/* 2. SLACK CARD */}
        {/* ================================================================= */}
        <div
          id="tool-card-slack"
          className="rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all hover:border-border"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400">
                <MessageSquare className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-foreground">Slack Webhook</h2>
                <p className="text-xs text-text-secondary">
                  Post formatted Block Kit meeting summaries and decisions
                </p>
              </div>
            </div>
            {getStatusBadge(integrations?.slack)}
          </div>

          {/* Current Details Preview */}
          <div className="mt-4 rounded-xl border border-border/60 bg-surface-2/60 p-3 text-xs space-y-1.5">
            <div className="flex justify-between">
              <span className="text-text-tertiary">Default Channel:</span>
              <span className="font-medium text-foreground">
                {integrations?.slack?.details?.channel || "#general"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-tertiary">Webhook URL:</span>
              <span className="font-mono text-foreground">
                {integrations?.slack?.details?.webhook_url_masked || "Not configured"}
              </span>
            </div>
          </div>

          {/* Test connection alert banner */}
          {testResults.slack && (
            <div
              className={`mt-3 flex items-start gap-2.5 rounded-xl border p-3 text-xs ${
                testResults.slack.success
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-red-500/30 bg-red-500/10 text-red-300"
              }`}
            >
              {testResults.slack.success ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
              )}
              <div className="flex-1">
                <p className="font-medium">{testResults.slack.message}</p>
                {testResults.slack.error && (
                  <p className="mt-0.5 text-[11px] opacity-90">{testResults.slack.error}</p>
                )}
              </div>
            </div>
          )}

          {/* Action Bar */}
          <div className="mt-4 flex items-center justify-between pt-3 border-t border-border/60">
            <div className="flex items-center gap-2">
              <button
                id="btn-test-slack"
                onClick={() =>
                  handleTestConnection(
                    "slack",
                    expandedCards.slack && slackForm.webhook_url ? slackForm : undefined
                  )
                }
                disabled={testingTool === "slack"}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-surface-2 disabled:opacity-50"
              >
                {testingTool === "slack" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
                ) : (
                  <Check className="h-3.5 w-3.5 text-text-tertiary" />
                )}
                Send Test Ping
              </button>

              {integrations?.slack?.is_custom && (
                <button
                  id="btn-disconnect-slack"
                  onClick={() => disconnectMutation.mutate("slack")}
                  disabled={disconnectMutation.isPending}
                  className="inline-flex items-center gap-1 rounded-lg border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-xs text-red-400 hover:bg-red-500/20"
                  title="Disconnect custom credentials and revert to workspace default"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Disconnect
                </button>
              )}
            </div>

            <button
              id="btn-expand-slack"
              onClick={() => toggleExpand("slack")}
              className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              {expandedCards.slack ? (
                <>
                  Close <ChevronUp className="h-3.5 w-3.5" />
                </>
              ) : (
                <>
                  Configure <ChevronDown className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>

          {/* Expanded Configuration Form */}
          {expandedCards.slack && (
            <form
              id="form-slack"
              onSubmit={(e) => {
                e.preventDefault();
                updateMutation.mutate({ tool: "slack", payload: slackForm });
              }}
              className="mt-4 space-y-3 rounded-xl border border-border bg-surface-2 p-3.5"
            >
              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-[11px] font-medium text-text-secondary">
                    Incoming Webhook URL
                  </label>
                  <a
                    href="https://api.slack.com/messaging/webhooks"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[10px] text-accent hover:underline"
                  >
                    Create Webhook <ExternalLink className="h-2.5 w-2.5" />
                  </a>
                </div>
                <input
                  id="input-slack-webhook"
                  type="url"
                  required
                  placeholder={
                    integrations?.slack?.details?.has_webhook_url
                      ? "Leave blank to keep existing webhook"
                      : "https://hooks.slack.com/services/..."
                  }
                  value={slackForm.webhook_url}
                  onChange={(e) =>
                    setSlackForm({ ...slackForm, webhook_url: e.target.value })
                  }
                  className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-text-secondary">
                  Notification Channel
                </label>
                <input
                  id="input-slack-channel"
                  type="text"
                  placeholder="#general or #product-team"
                  value={slackForm.channel}
                  onChange={(e) =>
                    setSlackForm({ ...slackForm, channel: e.target.value })
                  }
                  className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                />
              </div>

              <div className="flex justify-end pt-2">
                <button
                  id="btn-save-slack"
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="rounded-lg bg-accent px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:opacity-90 disabled:opacity-50"
                >
                  {updateMutation.isPending ? "Saving..." : "Save Slack Credentials"}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* ================================================================= */}
        {/* 3. SENDGRID / EMAIL CARD */}
        {/* ================================================================= */}
        <div
          id="tool-card-email"
          className="rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all hover:border-border"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-500/10 text-purple-400">
                <Mail className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-foreground">SendGrid Email</h2>
                <p className="text-xs text-text-secondary">
                  Dispatch personalized emails to meeting participants
                </p>
              </div>
            </div>
            {getStatusBadge(integrations?.email)}
          </div>

          {/* Current Details Preview */}
          <div className="mt-4 rounded-xl border border-border/60 bg-surface-2/60 p-3 text-xs space-y-1.5">
            <div className="flex justify-between">
              <span className="text-text-tertiary">Sender Email:</span>
              <span className="font-medium text-foreground">
                {integrations?.email?.details?.sender_email || "Not configured"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-tertiary">Display Name:</span>
              <span className="font-medium text-foreground">
                {integrations?.email?.details?.sender_name || "Meeting Intelligence Agent"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-tertiary">API Key:</span>
              <span className="font-mono text-foreground">
                {integrations?.email?.details?.api_key_masked || "None"}
              </span>
            </div>
          </div>

          {/* Test connection alert banner */}
          {testResults.email && (
            <div
              className={`mt-3 flex items-start gap-2.5 rounded-xl border p-3 text-xs ${
                testResults.email.success
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-red-500/30 bg-red-500/10 text-red-300"
              }`}
            >
              {testResults.email.success ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
              )}
              <div className="flex-1">
                <p className="font-medium">{testResults.email.message}</p>
                {testResults.email.error && (
                  <p className="mt-0.5 text-[11px] opacity-90">{testResults.email.error}</p>
                )}
              </div>
            </div>
          )}

          {/* Action Bar */}
          <div className="mt-4 flex items-center justify-between pt-3 border-t border-border/60">
            <div className="flex items-center gap-2">
              <button
                id="btn-test-email"
                onClick={() =>
                  handleTestConnection(
                    "email",
                    expandedCards.email && emailForm.sender_email ? emailForm : undefined
                  )
                }
                disabled={testingTool === "email"}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-surface-2 disabled:opacity-50"
              >
                {testingTool === "email" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
                ) : (
                  <Check className="h-3.5 w-3.5 text-text-tertiary" />
                )}
                Verify API Key
              </button>

              {integrations?.email?.is_custom && (
                <button
                  id="btn-disconnect-email"
                  onClick={() => disconnectMutation.mutate("email")}
                  disabled={disconnectMutation.isPending}
                  className="inline-flex items-center gap-1 rounded-lg border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-xs text-red-400 hover:bg-red-500/20"
                  title="Disconnect custom credentials and revert to workspace default"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Disconnect
                </button>
              )}
            </div>

            <button
              id="btn-expand-email"
              onClick={() => toggleExpand("email")}
              className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              {expandedCards.email ? (
                <>
                  Close <ChevronUp className="h-3.5 w-3.5" />
                </>
              ) : (
                <>
                  Configure <ChevronDown className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>

          {/* Expanded Configuration Form */}
          {expandedCards.email && (
            <form
              id="form-email"
              onSubmit={(e) => {
                e.preventDefault();
                updateMutation.mutate({ tool: "email", payload: emailForm });
              }}
              className="mt-4 space-y-3 rounded-xl border border-border bg-surface-2 p-3.5"
            >
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-text-secondary">
                    Verified Sender Email
                  </label>
                  <input
                    id="input-email-sender"
                    type="email"
                    required
                    placeholder="team@yourcompany.com"
                    value={emailForm.sender_email}
                    onChange={(e) =>
                      setEmailForm({ ...emailForm, sender_email: e.target.value })
                    }
                    className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-text-secondary">
                    Sender Display Name
                  </label>
                  <input
                    id="input-email-name"
                    type="text"
                    placeholder="Executive Meeting Assistant"
                    value={emailForm.sender_name}
                    onChange={(e) =>
                      setEmailForm({ ...emailForm, sender_name: e.target.value })
                    }
                    className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-[11px] font-medium text-text-secondary">
                    SendGrid API Key
                  </label>
                  <a
                    href="https://app.sendgrid.com/settings/api_keys"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[10px] text-accent hover:underline"
                  >
                    SendGrid Console <ExternalLink className="h-2.5 w-2.5" />
                  </a>
                </div>
                <div className="relative mt-1">
                  <input
                    id="input-email-key"
                    type={showEmailKey ? "text" : "password"}
                    placeholder={
                      integrations?.email?.details?.has_api_key
                        ? "Leave blank to keep existing key"
                        : "SG.xxxxxxxxxxxxxxxxxxxxxxxxxx"
                    }
                    value={emailForm.api_key}
                    onChange={(e) =>
                      setEmailForm({ ...emailForm, api_key: e.target.value })
                    }
                    className="w-full rounded-lg border border-border bg-surface px-3 py-1.5 pr-8 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                  />
                  <button
                    type="button"
                    onClick={() => setShowEmailKey(!showEmailKey)}
                    className="absolute right-2.5 top-2 text-text-tertiary hover:text-foreground"
                  >
                    {showEmailKey ? (
                      <EyeOff className="h-3.5 w-3.5" />
                    ) : (
                      <Eye className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  id="btn-save-email"
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="rounded-lg bg-accent px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:opacity-90 disabled:opacity-50"
                >
                  {updateMutation.isPending ? "Saving..." : "Save Email Credentials"}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* ================================================================= */}
        {/* 4. GOOGLE CALENDAR CARD */}
        {/* ================================================================= */}
        <div
          id="tool-card-calendar"
          className="rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all hover:border-border"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400">
                <Calendar className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-foreground">Google Calendar</h2>
                <p className="text-xs text-text-secondary">
                  Schedule follow-ups and invite participants automatically
                </p>
              </div>
            </div>
            {getStatusBadge(integrations?.calendar)}
          </div>

          {/* Current Details Preview */}
          <div className="mt-4 rounded-xl border border-border/60 bg-surface-2/60 p-3 text-xs space-y-1.5">
            <div className="flex justify-between">
              <span className="text-text-tertiary">Calendar ID:</span>
              <span className="font-medium text-foreground">
                {integrations?.calendar?.details?.calendar_id || "primary"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-tertiary">Service Account JSON:</span>
              <span className="font-mono text-foreground">
                {integrations?.calendar?.details?.has_credentials_json
                  ? "Configured (Service Account)"
                  : "Not configured"}
              </span>
            </div>
          </div>

          {/* Test connection alert banner */}
          {testResults.calendar && (
            <div
              className={`mt-3 flex items-start gap-2.5 rounded-xl border p-3 text-xs ${
                testResults.calendar.success
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-red-500/30 bg-red-500/10 text-red-300"
              }`}
            >
              {testResults.calendar.success ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
              )}
              <div className="flex-1">
                <p className="font-medium">{testResults.calendar.message}</p>
                {testResults.calendar.error && (
                  <p className="mt-0.5 text-[11px] opacity-90">{testResults.calendar.error}</p>
                )}
              </div>
            </div>
          )}

          {/* Action Bar */}
          <div className="mt-4 flex items-center justify-between pt-3 border-t border-border/60">
            <div className="flex items-center gap-2">
              <button
                id="btn-test-calendar"
                onClick={() =>
                  handleTestConnection(
                    "calendar",
                    expandedCards.calendar && calendarForm.calendar_id
                      ? calendarForm
                      : undefined
                  )
                }
                disabled={testingTool === "calendar"}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-surface-2 disabled:opacity-50"
              >
                {testingTool === "calendar" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
                ) : (
                  <Check className="h-3.5 w-3.5 text-text-tertiary" />
                )}
                Test Access
              </button>

              {integrations?.calendar?.is_custom && (
                <button
                  id="btn-disconnect-calendar"
                  onClick={() => disconnectMutation.mutate("calendar")}
                  disabled={disconnectMutation.isPending}
                  className="inline-flex items-center gap-1 rounded-lg border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-xs text-red-400 hover:bg-red-500/20"
                  title="Disconnect custom credentials and revert to workspace default"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Disconnect
                </button>
              )}
            </div>

            <button
              id="btn-expand-calendar"
              onClick={() => toggleExpand("calendar")}
              className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              {expandedCards.calendar ? (
                <>
                  Close <ChevronUp className="h-3.5 w-3.5" />
                </>
              ) : (
                <>
                  Configure <ChevronDown className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>

          {/* Expanded Configuration Form */}
          {expandedCards.calendar && (
            <form
              id="form-calendar"
              onSubmit={(e) => {
                e.preventDefault();
                updateMutation.mutate({ tool: "calendar", payload: calendarForm });
              }}
              className="mt-4 space-y-3 rounded-xl border border-border bg-surface-2 p-3.5"
            >
              <div>
                <label className="block text-[11px] font-medium text-text-secondary">
                  Target Calendar ID
                </label>
                <input
                  id="input-calendar-id"
                  type="text"
                  required
                  placeholder="primary or calendar-id@group.calendar.google.com"
                  value={calendarForm.calendar_id}
                  onChange={(e) =>
                    setCalendarForm({ ...calendarForm, calendar_id: e.target.value })
                  }
                  className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                />
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-[11px] font-medium text-text-secondary">
                    Service Account JSON
                  </label>
                  <a
                    href="https://console.cloud.google.com/iam-admin/serviceaccounts"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[10px] text-accent hover:underline"
                  >
                    GCP Console <ExternalLink className="h-2.5 w-2.5" />
                  </a>
                </div>
                <textarea
                  id="input-calendar-json"
                  rows={4}
                  placeholder={
                    integrations?.calendar?.details?.has_credentials_json
                      ? "Leave blank to keep existing credentials JSON"
                      : '{"type": "service_account", "project_id": "...", ...}'
                  }
                  value={calendarForm.credentials_json}
                  onChange={(e) =>
                    setCalendarForm({
                      ...calendarForm,
                      credentials_json: e.target.value,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-border bg-surface p-3 font-mono text-[11px] text-foreground placeholder:text-text-tertiary focus:border-accent focus:outline-hidden"
                />
              </div>

              <div className="flex justify-end pt-2">
                <button
                  id="btn-save-calendar"
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="rounded-lg bg-accent px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:opacity-90 disabled:opacity-50"
                >
                  {updateMutation.isPending ? "Saving..." : "Save Calendar Credentials"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
