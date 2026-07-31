import { cn } from "@/lib/utils";

export type ChatRole = "user" | "assistant";

type ChatBubbleProps = {
  role: ChatRole;
  message: string;
  timestamp?: string;
  isStreaming?: boolean;
};

export function ChatBubble({ role, message, timestamp, isStreaming }: ChatBubbleProps) {
  const isUser = role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] rounded-[16px] px-4 py-3 text-sm transition-all",
          isUser
            ? "bg-accent text-foreground"
            : "border border-border bg-surface text-text-secondary"
        )}
      >
        <p className="whitespace-pre-wrap leading-6">
          {message}
          {isStreaming ? (
            <span className="ml-1 inline-block animate-pulse font-bold text-accent">▍</span>
          ) : null}
        </p>
        {timestamp ? (
          <p className="mt-2 text-[11px] text-text-tertiary">{timestamp}</p>
        ) : null}
      </div>
    </div>
  );
}

