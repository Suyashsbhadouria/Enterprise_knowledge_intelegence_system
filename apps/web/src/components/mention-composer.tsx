"use client";

import * as React from "react";
import { BookOpen, Code2, FileText, FolderKanban, Hash, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { MentionSuggestion } from "@/lib/types";

function kindIcon(kind: string) {
  switch (kind) {
    case "slack_channel":
      return Hash;
    case "jira_issue":
      return FileText;
    case "jira_project":
      return FolderKanban;
    case "github_repo":
      return Code2;
    case "confluence_page":
      return BookOpen;
    default:
      return FileText;
  }
}

function getActiveMentionQuery(text: string, cursor: number): { start: number; query: string } | null {
  const before = text.slice(0, cursor);
  const at = before.lastIndexOf("@");
  if (at < 0) return null;
  if (at > 0 && /[a-zA-Z0-9_]/.test(before[at - 1] ?? "")) return null;
  const fragment = before.slice(at + 1);
  if (/\s/.test(fragment)) return null;
  return { start: at, query: fragment };
}

interface MentionComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

export function MentionComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder,
  className,
}: MentionComposerProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = React.useState(false);
  const [mentionStart, setMentionStart] = React.useState(0);
  const [query, setQuery] = React.useState("");
  const [suggestions, setSuggestions] = React.useState<MentionSuggestion[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [highlight, setHighlight] = React.useState(0);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSuggestions = React.useCallback(async (q: string) => {
    setLoading(true);
    try {
      const data = await api.mentionSuggest(q, 25);
      setSuggestions(data.suggestions);
      setHighlight(0);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const syncMentionState = React.useCallback(
    (text: string, cursor: number) => {
      const active = getActiveMentionQuery(text, cursor);
      if (!active) {
        setOpen(false);
        return;
      }
      setOpen(true);
      setMentionStart(active.start);
      setQuery(active.query);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        void fetchSuggestions(active.query);
      }, 180);
    },
    [fetchSuggestions],
  );

  const applySuggestion = (item: MentionSuggestion) => {
    const el = textareaRef.current;
    const cursor = el?.selectionStart ?? value.length;
    const before = value.slice(0, mentionStart);
    const after = value.slice(cursor);
    const insert = item.mention.endsWith(" ") ? item.mention : `${item.mention} `;
    const next = `${before}${insert}${after}`;
    onChange(next);
    setOpen(false);
    const nextCursor = before.length + insert.length;
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(nextCursor, nextCursor);
    });
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value;
    onChange(next);
    syncMentionState(next, e.target.selectionStart ?? next.length);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (open && suggestions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlight((i) => (i + 1) % suggestions.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlight((i) => (i - 1 + suggestions.length) % suggestions.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applySuggestion(suggestions[highlight]!);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  React.useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return (
    <div className="relative flex-1">
      {open && (
        <div
          className="absolute bottom-full left-0 right-0 mb-2 z-50 max-h-56 overflow-y-auto rounded-lg border bg-popover shadow-lg"
          role="listbox"
        >
          {loading && suggestions.length === 0 && (
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading…
            </div>
          )}
          {!loading && suggestions.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted-foreground">
              {query ? `No matches for “@${query}”` : "Type to filter channels, Jira, GitHub…"}
            </p>
          )}
          {suggestions.map((item, index) => {
            const Icon = kindIcon(item.kind);
            return (
              <button
                key={`${item.kind}-${item.mention}-${index}`}
                type="button"
                role="option"
                aria-selected={index === highlight}
                className={cn(
                  "w-full flex items-start gap-2 px-3 py-2 text-left text-sm hover:bg-accent",
                  index === highlight && "bg-accent",
                )}
                onMouseDown={(e) => {
                  e.preventDefault();
                  applySuggestion(item);
                }}
              >
                <Icon className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{item.label}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {item.mention}
                    {item.description ? ` · ${item.description}` : ""}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onClick={(e) =>
          syncMentionState(value, (e.target as HTMLTextAreaElement).selectionStart ?? value.length)
        }
        onFocus={() => {
          const el = textareaRef.current;
          if (el) syncMentionState(value, el.selectionStart ?? value.length);
        }}
        placeholder={placeholder}
        className={cn("min-h-[52px] max-h-32 resize-none", className)}
        disabled={disabled}
      />
    </div>
  );
}
