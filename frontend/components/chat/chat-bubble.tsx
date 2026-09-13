"use client";

import React, { useState } from "react";
import { Bot, User, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

export type ChatRole = "user" | "assistant";

type ChatBubbleProps = {
  role: ChatRole;
  message: string;
  timestamp?: string;
  isStreaming?: boolean;
  sources?: string[];
};

function renderFormattedText(text: string): React.ReactNode {
  // Split by inline code first
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code
          key={i}
          className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-foreground border border-border/50"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    // Handle **bold**
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
    return boldParts.map((bPart, j) => {
      if (bPart.startsWith("**") && bPart.endsWith("**") && bPart.length > 4) {
        return (
          <strong key={`${i}-${j}`} className="font-semibold text-foreground">
            {bPart.slice(2, -2)}
          </strong>
        );
      }
      return bPart;
    });
  });
}

function FormattedContent({ text }: { text: string }) {
  if (!text) return null;

  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let listBuffer: { type: "ul" | "ol"; items: string[] } | null = null;
  let inCodeBlock = false;
  let codeBuffer: string[] = [];
  let codeLang = "";

  const flushList = (key: number) => {
    if (!listBuffer) return null;
    const isUl = listBuffer.type === "ul";
    const current = listBuffer;
    listBuffer = null;
    return isUl ? (
      <ul key={`list-${key}`} className="my-2 ml-4 list-disc space-y-1 text-text-secondary">
        {current.items.map((item, idx) => (
          <li key={idx} className="leading-relaxed">
            {renderFormattedText(item)}
          </li>
        ))}
      </ul>
    ) : (
      <ol key={`list-${key}`} className="my-2 ml-4 list-decimal space-y-1 text-text-secondary">
        {current.items.map((item, idx) => (
          <li key={idx} className="leading-relaxed">
            {renderFormattedText(item)}
          </li>
        ))}
      </ol>
    );
  };

  lines.forEach((line, index) => {
    // Code block toggle
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        elements.push(
          <div
            key={`code-${index}`}
            className="my-3 overflow-x-auto rounded-lg border border-border bg-foreground/95 p-3 text-xs text-surface font-mono"
          >
            <pre>{codeBuffer.join("\n")}</pre>
          </div>
        );
        codeBuffer = [];
        inCodeBlock = false;
        codeLang = "";
      } else {
        if (listBuffer) elements.push(flushList(index));
        inCodeBlock = true;
        codeLang = line.trim().slice(3).trim();
      }
      return;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      return;
    }

    const trimmed = line.trim();

    // Check headers
    if (trimmed.startsWith("### ")) {
      if (listBuffer) elements.push(flushList(index));
      elements.push(
        <h4 key={`h4-${index}`} className="mt-3 mb-1.5 text-sm font-bold text-foreground">
          {renderFormattedText(trimmed.slice(4))}
        </h4>
      );
      return;
    }
    if (trimmed.startsWith("## ")) {
      if (listBuffer) elements.push(flushList(index));
      elements.push(
        <h3 key={`h3-${index}`} className="mt-4 mb-2 text-base font-bold text-foreground">
          {renderFormattedText(trimmed.slice(3))}
        </h3>
      );
      return;
    }
    if (trimmed.startsWith("# ")) {
      if (listBuffer) elements.push(flushList(index));
      elements.push(
        <h2 key={`h2-${index}`} className="mt-4 mb-2 text-lg font-bold text-foreground">
          {renderFormattedText(trimmed.slice(2))}
        </h2>
      );
      return;
    }

    // Bullet list items (- or *)
    const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (bulletMatch) {
      if (!listBuffer || listBuffer.type !== "ul") {
        if (listBuffer) elements.push(flushList(index));
        listBuffer = { type: "ul", items: [] };
      }
      listBuffer.items.push(bulletMatch[1]);
      return;
    }

    // Numbered list items
    const numMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (numMatch) {
      if (!listBuffer || listBuffer.type !== "ol") {
        if (listBuffer) elements.push(flushList(index));
        listBuffer = { type: "ol", items: [] };
      }
      listBuffer.items.push(numMatch[1]);
      return;
    }

    // Regular line / empty line
    if (listBuffer) {
      elements.push(flushList(index));
    }

    if (!trimmed) {
      elements.push(<div key={`spacer-${index}`} className="h-2" />);
    } else {
      elements.push(
        <p key={`p-${index}`} className="my-1 leading-relaxed text-text-secondary">
          {renderFormattedText(line)}
        </p>
      );
    }
  });

  if (listBuffer) {
    elements.push(flushList(lines.length));
  }
  if (inCodeBlock && codeBuffer.length > 0) {
    elements.push(
      <div
        key="code-end"
        className="my-3 overflow-x-auto rounded-lg border border-border bg-foreground/95 p-3 text-xs text-surface font-mono"
      >
        <pre>{codeBuffer.join("\n")}</pre>
      </div>
    );
  }

  return <div className="space-y-0.5">{elements}</div>;
}

export function ChatBubble({ role, message, timestamp, isStreaming, sources }: ChatBubbleProps) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);

  const copyToClipboard = async () => {
    if (!message) return;
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div className={cn("group flex w-full gap-3 py-1", isUser ? "flex-row-reverse" : "flex-row")}>
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium shadow-xs transition-transform",
          isUser
            ? "bg-accent text-white"
            : "bg-gradient-to-br from-amber-500/20 to-orange-500/30 text-amber-800 border border-amber-500/30"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Bubble Container */}
      <div className={cn("relative flex max-w-[85%] flex-col", isUser ? "items-end" : "items-start")}>
        <div
          className={cn(
            "relative rounded-2xl px-4 py-3 text-sm shadow-xs transition-all",
            isUser
              ? "bg-accent text-white rounded-tr-xs"
              : "border border-border bg-surface text-foreground rounded-tl-xs"
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap leading-relaxed text-white font-medium">{message}</p>
          ) : (
            <div>
              {message ? (
                <FormattedContent text={message} />
              ) : isStreaming ? (
                <div className="flex items-center gap-2 py-1 text-text-tertiary">
                  <span className="inline-block h-2 w-2 animate-ping rounded-full bg-accent" />
                  <span className="text-xs italic">Analyzing meeting context...</span>
                </div>
              ) : null}

              {isStreaming && message ? (
                <span className="ml-1 inline-block animate-pulse font-bold text-accent">▍</span>
              ) : null}
            </div>
          )}
        </div>

        {/* Sources / Citations */}
        {!isUser && sources && sources.length > 0 && !isStreaming ? (
          <div className="mt-1.5 flex flex-wrap gap-1.5 px-1">
            <span className="text-[10px] font-semibold tracking-wide uppercase text-text-tertiary">
              Sources:
            </span>
            {sources.map((src, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-text-secondary"
              >
                {src}
              </span>
            ))}
          </div>
        ) : null}

        {/* Footer: Timestamp & Copy action */}
        <div className="mt-1 flex items-center gap-2 px-1 text-[11px] text-text-tertiary">
          {timestamp ? <span>{timestamp}</span> : null}
          {!isUser && !isStreaming && message ? (
            <button
              onClick={copyToClipboard}
              className="inline-flex items-center gap-1 text-[10px] text-text-tertiary hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
              title="Copy message"
            >
              {copied ? (
                <>
                  <Check className="h-3 w-3 text-emerald-600" />
                  <span className="text-emerald-600">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
