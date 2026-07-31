"use client";

import { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { useAgentChatStream } from "@/lib/hooks/use-agent-chat";
import { ChatBubble } from "@/components/chat/chat-bubble";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function AgentChatPage() {
  const { streamQuery, isStreaming } = useAgentChatStream();
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<{ role: "user" | "assistant"; message: string; isStreaming?: boolean }[]>([
    {
      role: "assistant",
      message: "Hi, I am your meeting intelligence agent. Ask anything about your meetings or next steps.",
    },
  ]);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread]);

  const sendMessage = async () => {
    const content = message.trim();
    if (!content || isStreaming) return;

    setThread((prev) => [
      ...prev,
      { role: "user", message: content },
      { role: "assistant", message: "", isStreaming: true },
    ]);
    setMessage("");

    try {
      await streamQuery(
        { question: content },
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
        () => {
          setThread((prev) => {
            const updated = [...prev];
            const lastIndex = updated.length - 1;
            if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
              updated[lastIndex] = {
                ...updated[lastIndex],
                isStreaming: false,
              };
            }
            return updated;
          });
        }
      );
    } catch {
      toast.error("Agent is unavailable. Try again shortly.");
      setThread((prev) => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        if (lastIndex >= 0 && updated[lastIndex].role === "assistant" && !updated[lastIndex].message) {
          updated[lastIndex] = {
            role: "assistant",
            message: "Sorry, I couldn't process your request right now.",
            isStreaming: false,
          };
        } else if (lastIndex >= 0) {
          updated[lastIndex].isStreaming = false;
        }
        return updated;
      });
    }
  };

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-4xl flex-col rounded-[20px] border border-border bg-surface p-5">
      <div className="border-b border-border pb-3">
        <p className="text-xs uppercase tracking-[0.22em] text-text-tertiary">Agent Chat</p>
        <h2 className="heading-title mt-2 text-foreground">Talk to the intelligence layer</h2>
      </div>

      <div className="flex-1 space-y-4 overflow-auto py-6">
        {thread.map((entry, index) => (
          <ChatBubble
            key={index}
            role={entry.role}
            message={entry.message}
            isStreaming={entry.isStreaming}
          />
        ))}
        <div ref={chatBottomRef} />
      </div>

      <div className="flex gap-2 border-t border-border pt-4">
        <Input
          placeholder="Ask about meetings, follow-ups, or summaries"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void sendMessage();
            }
          }}
          disabled={isStreaming}
        />
        <Button onClick={() => void sendMessage()} disabled={isStreaming || !message.trim()}>
          {isStreaming ? "Thinking..." : "Send"}
        </Button>
      </div>
    </div>
  );
}

