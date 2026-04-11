"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useAgentChat } from "@/lib/hooks/use-agent-chat";
import { ChatBubble } from "@/components/chat/chat-bubble";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function AgentChatPage() {
  const chatMutation = useAgentChat();
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<{ role: "user" | "assistant"; message: string }[]>([
    {
      role: "assistant",
      message: "Hi, I am your meeting intelligence agent. Ask anything about your meetings or next steps.",
    },
  ]);

  const sendMessage = async () => {
    const content = message.trim();
    if (!content) return;
    setThread((prev) => [...prev, { role: "user", message: content }]);
    setMessage("");

    try {
      const response = await chatMutation.mutateAsync({ question: content });
      setThread((prev) => [...prev, { role: "assistant", message: response.answer }]);
    } catch {
      toast.error("Agent is unavailable. Try again shortly.");
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
          <ChatBubble key={index} role={entry.role} message={entry.message} />
        ))}
        {chatMutation.isPending ? (
          <ChatBubble role="assistant" message="Thinking..." />
        ) : null}
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
        />
        <Button onClick={() => void sendMessage()} disabled={chatMutation.isPending}>
          Send
        </Button>
      </div>
    </div>
  );
}
