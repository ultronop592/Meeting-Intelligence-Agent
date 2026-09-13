"use client";

import { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import {
  Bot,
  Sparkles,
  Send,
  Trash2,
  Calendar,
  ChevronDown,
  Layers,
} from "lucide-react";
import { useAgentChatStream } from "@/lib/hooks/use-agent-chat";
import { useMeetings } from "@/lib/hooks/use-meetings";
import { ChatBubble } from "@/components/chat/chat-bubble";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/types/api";

const QUICK_PROMPTS = [
  {
    label: "Key Decisions",
    query: "What were the key decisions made during this meeting and what context was provided?",
  },
  {
    label: "Action Items & Owners",
    query: "List all action items with their designated owners, priorities, and deadlines.",
  },
  {
    label: "Participant Breakdown",
    query: "Who were the active speakers and what key points did each participant contribute?",
  },
  {
    label: "Executive Summary",
    query: "Provide a 3-bullet high-level executive summary of this meeting with blockers highlighted.",
  },
];

type ChatThreadItem = {
  role: "user" | "assistant";
  message: string;
  isStreaming?: boolean;
  sources?: string[];
  timestamp?: string;
};

export default function AgentChatPage() {
  const { streamQuery, isStreaming } = useAgentChatStream();
  const { data: meetings, isLoading: isLoadingMeetings } = useMeetings();
  const [selectedMeetingId, setSelectedMeetingId] = useState<string>("");
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<ChatThreadItem[]>([
    {
      role: "assistant",
      message:
        "Hello! I am your AI Meeting Intelligence Agent with complete context awareness across your meetings.\n\nSelect a meeting above or ask anything across all your recorded meetings.",
      timestamp: "Just now",
    },
  ]);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread]);

  const selectedMeeting = meetings?.find((m) => m.id === selectedMeetingId);

  const handleClearChat = () => {
    setThread([
      {
        role: "assistant",
        message: selectedMeeting
          ? `Cleared! Full transcript and metadata for **${selectedMeeting.title}** are loaded. What would you like to know?`
          : "Cleared! I am ready to answer any questions across all your meetings.",
        timestamp: "Just now",
      },
    ]);
  };

  const handleSelectMeeting = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newId = e.target.value;
    setSelectedMeetingId(newId);
    if (newId) {
      const found = meetings?.find((m) => m.id === newId);
      if (found) {
        setThread((prev) => [
          ...prev,
          {
            role: "assistant",
            message: `Context switched to: **${found.title}**\nFull diarized transcript, decisions, action items, and participants have been loaded into my active memory.`,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
      }
    }
  };

  const sendMessage = async (textToSend?: string) => {
    const content = (textToSend ?? message).trim();
    if (!content || isStreaming) return;

    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    // Build conversation history (up to last 8 turns)
    const history: ChatMessage[] = thread
      .filter((t) => !t.isStreaming && t.message.trim().length > 0)
      .slice(-8)
      .map((t) => ({
        role: t.role,
        content: t.message,
      }));

    setThread((prev) => [
      ...prev,
      { role: "user", message: content, timestamp: timeStr },
      { role: "assistant", message: "", isStreaming: true, timestamp: timeStr },
    ]);
    if (!textToSend) setMessage("");

    try {
      await streamQuery(
        {
          question: content,
          meeting_id: selectedMeetingId || undefined,
          history,
        },
        (chunk) => {
          setThread((prev) => {
            const updated = [...prev];
            const lastIndex = updated.length - 1;
            if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
              updated[lastIndex] = {
                ...updated[lastIndex],
                message: updated[lastIndex].message + chunk,
              };
            }
            return updated;
          });
        },
        (sources) => {
          setThread((prev) => {
            const updated = [...prev];
            const lastIndex = updated.length - 1;
            if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
              updated[lastIndex] = {
                ...updated[lastIndex],
                isStreaming: false,
                sources: sources && sources.length > 0 ? sources : undefined,
              };
            }
            return updated;
          });
        }
      );
    } catch {
      toast.error("Agent query failed. Please check backend connection.");
      setThread((prev) => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
          if (!updated[lastIndex].message) {
            updated[lastIndex] = {
              ...updated[lastIndex],
              role: "assistant",
              message: "Sorry, I encountered an issue retrieving the response from the LLM. Please try again.",
              isStreaming: false,
            };
          } else {
            updated[lastIndex] = {
              ...updated[lastIndex],
              isStreaming: false,
            };
          }
        }
        return updated;
      });
    }
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-6rem)] max-w-5xl flex-col rounded-3xl border border-border bg-surface shadow-xs">
      {/* Top Header Bar */}
      <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-accent/15 text-accent">
              <Bot className="h-3.5 w-3.5" />
            </span>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-text-tertiary">
              Meeting Intelligence Agent
            </p>
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground sm:text-xl">
            Conversational Agent Chat
          </h1>
        </div>

        {/* Model Status & Clear Action */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-2 px-3 py-1 text-xs text-text-secondary">
            <Sparkles className="h-3.5 w-3.5 text-accent" />
            <span className="font-medium text-foreground">Intelligence Active</span>
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleClearChat}
            className="h-8 gap-1.5 text-xs text-text-secondary hover:text-danger"
            title="Reset conversation"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>Reset</span>
          </Button>
        </div>
      </div>

      {/* Context Selector Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/80 bg-surface-2/60 px-4 py-2.5 sm:px-6">
        <div className="flex flex-1 items-center gap-2 min-w-[280px]">
          <Layers className="h-4 w-4 text-text-tertiary shrink-0" />
          <span className="text-xs font-medium text-text-secondary shrink-0">Context Scope:</span>
          <div className="relative flex-1 max-w-md">
            <select
              value={selectedMeetingId}
              onChange={handleSelectMeeting}
              disabled={isLoadingMeetings || isStreaming}
              className="w-full appearance-none rounded-lg border border-border bg-surface px-3 py-1.5 pr-8 text-xs font-medium text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
            >
              <option value="">All Meetings (Cross-meeting global context)</option>
              {meetings?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title} ({m.duration_minutes ? `${Math.round(m.duration_minutes)}m` : "Recorded"})
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-tertiary" />
          </div>
        </div>

        {selectedMeeting ? (
          <div className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-2.5 py-1">
            <Calendar className="h-3 w-3 shrink-0" />
            <span className="font-medium truncate max-w-[220px]">
              {selectedMeeting.title}
            </span>
            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 bg-emerald-500/15 rounded px-1.5 py-0.5">
              Full context active
            </span>
          </div>
        ) : (
          <div className="text-xs text-text-tertiary">
            Full intelligence repository enabled
          </div>
        )}
      </div>

      {/* Chat Messages Body */}
      <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
        {thread.map((entry, index) => (
          <ChatBubble
            key={index}
            role={entry.role}
            message={entry.message}
            isStreaming={entry.isStreaming}
            sources={entry.sources}
            timestamp={entry.timestamp}
          />
        ))}
        <div ref={chatBottomRef} />
      </div>

      {/* Prompt Suggestions Bar */}
      <div className="border-t border-border/80 bg-surface-2/40 px-4 py-2 sm:px-6">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
          <Sparkles className="h-3.5 w-3.5 text-accent shrink-0" />
          <span className="text-[11px] font-semibold text-text-tertiary shrink-0 mr-1">
            Suggestions:
          </span>
          {QUICK_PROMPTS.map((prompt, idx) => (
            <button
              key={idx}
              onClick={() => void sendMessage(prompt.query)}
              disabled={isStreaming}
              className="inline-flex shrink-0 items-center rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-medium text-text-secondary shadow-2xs hover:border-accent hover:text-accent disabled:opacity-50 transition-colors"
            >
              {prompt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Message Input Form */}
      <div className="border-t border-border p-3 sm:p-4 bg-surface rounded-b-3xl">
        <div className="relative flex items-end gap-2 rounded-2xl border border-border bg-surface-2/70 p-1.5 focus-within:border-accent focus-within:ring-1 focus-within:ring-accent transition-all">
          <textarea
            ref={inputRef}
            rows={1}
            placeholder={
              selectedMeeting
                ? `Ask anything about "${selectedMeeting.title}"...`
                : "Ask anything about decisions, action items, or meetings..."
            }
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void sendMessage();
              }
            }}
            disabled={isStreaming}
            className="flex-1 resize-none bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-text-tertiary focus:outline-none disabled:opacity-50 min-h-[42px] max-h-32"
          />

          <Button
            onClick={() => void sendMessage()}
            disabled={isStreaming || !message.trim()}
            size="sm"
            className="h-9 w-9 rounded-xl p-0 bg-accent hover:bg-accent-strong text-white shrink-0 shadow-xs"
            title="Send message (Enter)"
          >
            {isStreaming ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>

        <div className="mt-1.5 flex items-center justify-between px-2 text-[11px] text-text-tertiary">
          <span>
            Press <kbd className="rounded border border-border bg-surface px-1 py-0.5 font-mono text-[10px]">Enter</kbd> to send, <kbd className="rounded border border-border bg-surface px-1 py-0.5 font-mono text-[10px]">Shift + Enter</kbd> for new line
          </span>
          <span>Meeting Intelligence AI</span>
        </div>
      </div>
    </div>
  );
}
