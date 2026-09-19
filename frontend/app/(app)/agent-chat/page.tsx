"use client";

import React, { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Sparkles,
  Send,
  Trash2,
  Calendar,
  ChevronDown,
  Layers,
  MessageSquare,
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  Clock,
  ExternalLink,
} from "lucide-react";
import {
  useAgentChatStream,
  useChatSessions,
  useChatSession,
  useDeleteChatSession,
} from "@/lib/hooks/use-agent-chat";
import { useMeetings } from "@/lib/hooks/use-meetings";
import { ChatBubble } from "@/components/chat/chat-bubble";
import { ChatSuggestions } from "@/components/chat/chat-suggestions";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/types/api";

type ChatThreadItem = {
  role: "user" | "assistant";
  message: string;
  isStreaming?: boolean;
  sources?: string[];
  timestamp?: string;
};

export default function AgentChatPage() {
  const queryClient = useQueryClient();
  const { streamQuery, isStreaming } = useAgentChatStream();
  const { data: meetings, isLoading: isLoadingMeetings } = useMeetings();

  // Session state
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Queries & Mutations
  const { data: sessions, isLoading: isLoadingSessions } = useChatSessions();
  const { data: activeSessionData, isLoading: isLoadingSessionDetail } = useChatSession(activeSessionId);
  const deleteSessionMutation = useDeleteChatSession();

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

  // Auto-scroll on new messages
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread]);

  // When active session data loads, populate the thread
  useEffect(() => {
    if (activeSessionData && activeSessionId === activeSessionData.id) {
      if (activeSessionData.meeting_id) {
        setSelectedMeetingId(activeSessionData.meeting_id);
      }

      if (activeSessionData.messages && activeSessionData.messages.length > 0) {
        const mapped: ChatThreadItem[] = activeSessionData.messages.map((m) => ({
          role: m.role === "assistant" ? "assistant" : "user",
          message: m.content,
          timestamp: m.timestamp || undefined,
          sources: m.sources || undefined,
        }));
        setThread(mapped);
      } else {
        setThread([
          {
            role: "assistant",
            message: `Starting conversation: **${activeSessionData.title}**. What would you like to discuss?`,
            timestamp: "Just now",
          },
        ]);
      }
    }
  }, [activeSessionData, activeSessionId]);

  const selectedMeeting = meetings?.find((m) => m.id === selectedMeetingId);

  const handleStartNewChat = () => {
    setActiveSessionId(null);
    setThread([
      {
        role: "assistant",
        message: selectedMeeting
          ? `Started a new conversation with context set to **${selectedMeeting.title}**. Ask anything about this meeting!`
          : "Started a new conversation! I have full intelligence access across all your meetings. What would you like to know?",
        timestamp: "Just now",
      },
    ]);
  };

  const handleSelectSession = (sessionId: string) => {
    if (isStreaming) return;
    setActiveSessionId(sessionId);
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await deleteSessionMutation.mutateAsync(sessionId);
      toast.success("Chat conversation deleted");
      if (activeSessionId === sessionId) {
        handleStartNewChat();
      }
    } catch {
      toast.error("Failed to delete chat session");
    }
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
            message: `Context scoped to: **${found.title}**\nFull diarized transcript, decisions, action items, and participants loaded.`,
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

    // Build conversation history (up to last 10 turns)
    const history: ChatMessage[] = thread
      .filter((t) => !t.isStreaming && t.message.trim().length > 0)
      .slice(-10)
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
          session_id: activeSessionId || undefined,
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
        (sources, returnedSessionId) => {
          if (returnedSessionId && returnedSessionId !== activeSessionId) {
            setActiveSessionId(returnedSessionId);
            queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
          }
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
    <div className="mx-auto flex h-[calc(100vh-6.5rem)] max-w-7xl overflow-hidden rounded-3xl border border-border bg-surface shadow-xs">
      {/* Collapsible Chat Sessions Sidebar */}
      <div
        className={`${
          isSidebarOpen ? "w-72" : "w-0"
        } hidden md:flex flex-col border-r border-border bg-surface-2/60 transition-all duration-300 ease-in-out overflow-hidden shrink-0`}
      >
        {/* Sidebar Header */}
        <div className="flex items-center justify-between border-b border-border p-3.5">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-accent" />
            <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">
              Conversations
            </span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleStartNewChat}
            className="h-7 gap-1 px-2 text-xs font-semibold"
            title="Start new conversation"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New Chat</span>
          </Button>
        </div>

        {/* Sessions List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin">
          {isLoadingSessions ? (
            <div className="p-4 text-center text-xs text-text-tertiary">
              Loading chat sessions...
            </div>
          ) : !sessions || sessions.length === 0 ? (
            <div className="p-4 text-center text-xs text-text-tertiary">
              No conversations yet. Start asking questions!
            </div>
          ) : (
            sessions.map((sess) => {
              const isActive = sess.id === activeSessionId;
              return (
                <div
                  key={sess.id}
                  onClick={() => handleSelectSession(sess.id)}
                  className={`group relative flex cursor-pointer items-start justify-between rounded-xl p-2.5 transition-all ${
                    isActive
                      ? "bg-accent/10 border border-accent/25 text-foreground shadow-2xs"
                      : "hover:bg-surface text-text-secondary hover:text-foreground"
                  }`}
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <p className="truncate text-xs font-semibold leading-tight">
                      {sess.title || "Untitled Session"}
                    </p>
                    {sess.preview && (
                      <p className="mt-0.5 truncate text-[11px] text-text-tertiary">
                        {sess.preview}
                      </p>
                    )}
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-text-tertiary">
                      <span className="flex items-center gap-0.5">
                        <Clock className="h-2.5 w-2.5" />
                        {sess.message_count} msgs
                      </span>
                      {sess.meeting_title && (
                        <span className="truncate max-w-[110px] rounded bg-surface px-1 py-0.2 border border-border/60">
                          {sess.meeting_title}
                        </span>
                      )}
                    </div>
                  </div>

                  <button
                    onClick={(e) => handleDeleteSession(e, sess.id)}
                    className="opacity-0 group-hover:opacity-100 hover:text-danger rounded p-1 text-text-tertiary transition-opacity"
                    title="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Main Chat Container */}
      <div className="flex flex-1 flex-col min-w-0 bg-surface">
        {/* Top Header Bar */}
        <div className="flex flex-col gap-3 border-b border-border p-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="hidden md:inline-flex h-8 w-8 p-0 text-text-secondary"
              title={isSidebarOpen ? "Collapse sidebar" : "Open sidebar"}
            >
              {isSidebarOpen ? (
                <PanelLeftClose className="h-4 w-4" />
              ) : (
                <PanelLeftOpen className="h-4 w-4" />
              )}
            </Button>

            <div>
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-md bg-accent/15 text-accent">
                  <Bot className="h-3 w-3" />
                </span>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-tertiary">
                  Meeting Intelligence Agent
                </p>
              </div>
              <h1 className="text-base font-semibold tracking-tight text-foreground sm:text-lg">
                Conversational Memory Chat
              </h1>
            </div>
          </div>

          {/* Model Status & Actions */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-2 px-3 py-1 text-xs text-text-secondary">
              <Sparkles className="h-3.5 w-3.5 text-accent" />
              <span className="font-medium text-foreground">Multi-Turn Memory</span>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={handleStartNewChat}
              className="h-8 gap-1.5 text-xs text-text-secondary hover:text-foreground"
              title="Start fresh conversation"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>New Chat</span>
            </Button>
          </div>
        </div>

        {/* Context Selector Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/80 bg-surface-2/60 px-4 py-2 sm:px-6">
          <div className="flex flex-1 items-center gap-2 min-w-[260px]">
            <Layers className="h-4 w-4 text-text-tertiary shrink-0" />
            <span className="text-xs font-medium text-text-secondary shrink-0">
              Context Scope:
            </span>
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
              <span className="font-medium truncate max-w-[200px]">
                {selectedMeeting.title}
              </span>
              <span className="text-[10px] text-emerald-600 dark:text-emerald-400 bg-emerald-500/15 rounded px-1.5 py-0.5">
                Scoped
              </span>
            </div>
          ) : (
            <div className="text-xs text-text-tertiary hidden sm:block">
              Global repository memory active
            </div>
          )}
        </div>

        {/* Chat Messages Body */}
        <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6 scrollbar-thin">
          {isLoadingSessionDetail && activeSessionId ? (
            <div className="flex items-center justify-center py-12 text-xs text-text-tertiary">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent mr-2" />
              Loading session history...
            </div>
          ) : (
            thread.map((entry, index) => (
              <ChatBubble
                key={index}
                role={entry.role}
                message={entry.message}
                isStreaming={entry.isStreaming}
                sources={entry.sources}
                timestamp={entry.timestamp}
              />
            ))
          )}
          <div ref={chatBottomRef} />
        </div>

        {/* Quick Suggestion Chips Component */}
        <ChatSuggestions
          onSelectPrompt={(promptQuery) => void sendMessage(promptQuery)}
          disabled={isStreaming}
          meetingTitle={selectedMeeting?.title}
        />

        {/* Message Input Bar */}
        <div className="border-t border-border p-3 sm:p-4 bg-surface rounded-b-3xl">
          <div className="relative flex items-end gap-2 rounded-2xl border border-border bg-surface-2/70 p-1.5 focus-within:border-accent focus-within:ring-1 focus-within:ring-accent transition-all">
            <textarea
              ref={inputRef}
              rows={1}
              placeholder={
                selectedMeeting
                  ? `Ask anything about "${selectedMeeting.title}"...`
                  : "Ask anything about decisions, action items, or past meetings..."
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
            <span>Meeting Intelligence Multi-Turn AI</span>
          </div>
        </div>
      </div>
    </div>
  );
}
