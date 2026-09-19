"use client";

import React from "react";
import { Sparkles, CheckSquare, Lightbulb, Users, FileText, AlertCircle } from "lucide-react";

export type SuggestionPrompt = {
  id: string;
  label: string;
  query: string;
  icon?: React.ReactNode;
  category?: string;
};

interface ChatSuggestionsProps {
  onSelectPrompt: (query: string) => void;
  disabled?: boolean;
  meetingTitle?: string | null;
}

const DEFAULT_PROMPTS: SuggestionPrompt[] = [
  {
    id: "decisions",
    label: "Key Decisions",
    query: "What were the key decisions made during this meeting and what context was provided for each?",
    icon: <Lightbulb className="h-3 w-3 text-amber-500" />,
    category: "Decisions",
  },
  {
    id: "action_items",
    label: "Action Items & Owners",
    query: "List all action items with their designated owners, priorities, and deadlines.",
    icon: <CheckSquare className="h-3 w-3 text-emerald-500" />,
    category: "Tasks",
  },
  {
    id: "participants",
    label: "Participant Breakdown",
    query: "Who were the active speakers and what key points or concerns did each participant contribute?",
    icon: <Users className="h-3 w-3 text-sky-500" />,
    category: "Speakers",
  },
  {
    id: "exec_summary",
    label: "Executive Summary",
    query: "Provide a 3-bullet high-level executive summary of this meeting with blockers highlighted.",
    icon: <FileText className="h-3 w-3 text-purple-500" />,
    category: "Summary",
  },
  {
    id: "blockers",
    label: "Risks & Blockers",
    query: "Were there any critical risks, technical debt, or blockers identified in the discussion?",
    icon: <AlertCircle className="h-3 w-3 text-rose-500" />,
    category: "Risks",
  },
];

export function ChatSuggestions({
  onSelectPrompt,
  disabled = false,
  meetingTitle,
}: ChatSuggestionsProps) {
  return (
    <div className="border-t border-border/70 bg-surface-2/40 px-4 py-2.5 sm:px-6">
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
        <div className="flex items-center gap-1.5 shrink-0 text-text-tertiary mr-1">
          <Sparkles className="h-3.5 w-3.5 text-accent" />
          <span className="text-[11px] font-semibold tracking-wide uppercase">
            Suggested
          </span>
        </div>

        <div className="flex items-center gap-2">
          {DEFAULT_PROMPTS.map((prompt) => (
            <button
              key={prompt.id}
              type="button"
              onClick={() => onSelectPrompt(prompt.query)}
              disabled={disabled}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border/80 bg-surface px-3 py-1 text-xs font-medium text-text-secondary shadow-2xs transition-all hover:border-accent hover:text-accent hover:shadow-xs active:scale-95 disabled:pointer-events-none disabled:opacity-40"
              title={prompt.query}
            >
              {prompt.icon}
              <span>{prompt.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
