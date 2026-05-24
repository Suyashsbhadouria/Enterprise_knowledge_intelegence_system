"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { User, Bot, Check, X, ExternalLink, Send, Loader2, BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MentionComposer } from "@/components/mention-composer";
import { isActionAwaitingApproval, type ChatMessage } from "@/lib/chat-actions";
import type { Citation, ProposedAction } from "@/lib/types";

const markdownComponents: Components = {
  p: ({ children, ...props }) => (
    <p className="text-sm leading-relaxed mb-2 last:mb-0" {...props}>{children}</p>
  ),
  ul: ({ children, ...props }) => (
    <ul className="list-disc list-outside space-y-0.5 text-sm mb-2 pl-4" {...props}>{children}</ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="list-decimal list-outside space-y-0.5 text-sm mb-2 pl-5" {...props}>{children}</ol>
  ),
  code: ({ children, className, ...props }) => {
    const isBlock = typeof className === "string" && className.startsWith("language-");
    if (isBlock) return <code className={className} {...props}>{children}</code>;
    return (
      <code className="px-1 py-0.5 rounded bg-secondary text-[0.875em] font-mono" {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children, ...props }) => (
    <pre className="my-3 p-3 rounded-lg border bg-secondary overflow-x-auto text-xs font-mono" {...props}>
      {children}
    </pre>
  ),
  a: ({ href, children, ...props }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline" {...props}>
      {children}
    </a>
  ),
};

interface SourcesListProps {
  citations: Citation[];
}

function SourcesList({ citations }: SourcesListProps) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <motion.div layout className="mt-3 w-full rounded-xl border bg-muted/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((open) => !open)}
        className="w-full px-3 py-2 bg-muted/50 flex items-center gap-2 text-left hover:bg-muted/70 transition-colors"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        )}
        <BookOpen className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Sources
        </span>
        <span className="text-xs text-muted-foreground">({citations.length})</span>
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.ul
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="divide-y overflow-hidden"
          >
            {citations.map((cite) => (
              <li key={`${cite.source}:${cite.source_id}`} className="px-3 py-2.5">
                <motion.div
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-start justify-between gap-3"
                >
                  <motion.div className="min-w-0 flex-1">
                    <p className="text-sm font-medium leading-snug line-clamp-2">{cite.title}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="text-[10px] font-normal">
                        {cite.source}
                      </Badge>
                      <span className="text-xs text-muted-foreground font-mono">{cite.source_id}</span>
                    </div>
                    {cite.excerpt && (
                      <p className="mt-1.5 text-xs text-muted-foreground line-clamp-2">{cite.excerpt}</p>
                    )}
                  </motion.div>
                  {cite.url && (
                    <a
                      href={cite.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 rounded-md p-1.5 text-primary hover:bg-primary/10"
                      aria-label={`Open ${cite.title}`}
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  )}
                </motion.div>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function actionStatusLabel(status: string): string {
  if (status === "executed" || status === "approved") return "Approved";
  if (status === "rejected") return "Rejected";
  if (status === "failed") return "Failed";
  return "Awaiting approval";
}

function actionCardClass(status: string): string {
  if (isActionAwaitingApproval(status)) {
    return "border-amber-200/60 bg-amber-50/50 dark:border-amber-900/50 dark:bg-amber-950/20";
  }
  if (status === "executed" || status === "approved") {
    return "border-green-200/60 bg-green-50/50 dark:border-green-900/50 dark:bg-green-950/20";
  }
  if (status === "rejected" || status === "failed") {
    return "border-red-200/60 bg-red-50/50 dark:border-red-900/50 dark:bg-red-950/20";
  }
  return "border-border bg-muted/30";
}

function actionBadgeClass(status: string): string {
  if (isActionAwaitingApproval(status)) {
    return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300";
  }
  if (status === "executed" || status === "approved") {
    return "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300";
  }
  if (status === "rejected" || status === "failed") {
    return "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300";
  }
  return "bg-secondary text-secondary-foreground";
}

interface ActionApprovalCardProps {
  action: ProposedAction;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  loading?: boolean;
}

function ActionApprovalCard({ action, onApprove, onReject, loading }: ActionApprovalCardProps) {
  const awaiting = isActionAwaitingApproval(action.status);

  return (
    <Card className={cn("mt-3 p-4", actionCardClass(action.status))}>
      <motion.div
        className="space-y-3"
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Proposed action
            </p>
            <p className="text-sm mt-2">{action.preview}</p>
          </div>
          <Badge className={cn("shrink-0", actionBadgeClass(action.status))}>
            {actionStatusLabel(action.status)}
          </Badge>
        </div>
        {awaiting ? (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => onApprove(action.id)} disabled={loading} className="flex-1">
              {loading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Check className="w-4 h-4 mr-1" />}
              Approve
            </Button>
            <Button size="sm" variant="outline" onClick={() => onReject(action.id)} disabled={loading} className="flex-1">
              <X className="w-4 h-4 mr-1" /> Reject
            </Button>
          </div>
        ) : (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-xs text-muted-foreground"
          >
            {action.status === "executed" || action.status === "approved"
              ? "This action was approved and executed."
              : action.status === "rejected"
                ? "This action was rejected."
                : action.status === "failed"
                  ? action.error ?? "This action failed to execute."
                  : null}
          </motion.p>
        )}
      </motion.div>
    </Card>
  );
}

interface ChatInterfaceProps {
  messages: ChatMessage[];
  onSend: (content: string) => Promise<void>;
  onApproveAction: (actionId: string) => Promise<void>;
  onRejectAction: (actionId: string) => Promise<void>;
  loading?: boolean;
}

export function ChatInterface({
  messages,
  onSend,
  onApproveAction,
  onRejectAction,
  loading,
}: ChatInterfaceProps) {
  const [input, setInput] = React.useState("");
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);
  const endRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    await onSend(text);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex flex-col h-[calc(100vh-8rem)] border rounded-2xl bg-card overflow-hidden shadow-sm"
    >
      <div className="px-6 py-4 border-b bg-secondary/30 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <motion.div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Bot className="w-6 h-6 text-primary" />
          </motion.div>
          <div>
            <h2 className="text-sm font-semibold">Knowledge Assistant</h2>
            <div className="flex items-center gap-2">
              <motion.div
                className={cn("w-2 h-2 rounded-full", loading ? "bg-amber-500 animate-pulse" : "bg-green-500")}
                animate={{ opacity: loading ? 0.85 : 1 }}
              />
              <span className="text-xs text-muted-foreground">
                {loading ? "Thinking…" : "Ready"}
              </span>
            </div>
          </div>
        </div>
      </div>

      <motion.div layout className="flex-1 overflow-y-auto px-6 py-4">
        <AnimatePresence mode="popLayout">
          {messages.length === 0 && (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-center py-16 text-muted-foreground"
            >
              <Bot className="w-12 h-12 mx-auto mb-4 opacity-40" />
              <p className="text-sm">Ask about Jira, Confluence, GitHub, Slack, or meeting transcripts.</p>
              <p className="text-xs mt-2">
                Type <span className="font-mono">@</span> to mention Slack channels, Jira tickets, GitHub repos, and more.
              </p>
            </motion.div>
          )}
          {messages.map((msg) => {
            const isUser = msg.role === "user";
            const assistantText = msg.displayContent ?? msg.content;
            const citations = msg.citations ?? [];
            const actionsToShow = msg.proposedActions ?? [];

            return (
              <motion.div
                key={msg.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ type: "spring", stiffness: 380, damping: 28 }}
                className={cn("flex gap-3 mb-6", isUser ? "justify-end" : "justify-start")}
              >
                {!isUser && (
                  <div className="shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <Bot className="w-5 h-5 text-primary" />
                  </div>
                )}
                <div className={cn("flex flex-col max-w-[85%]", isUser && "items-end")}>
                  <motion.div
                    layout
                    className={cn(
                      "rounded-2xl px-4 py-3",
                      isUser ? "bg-primary text-primary-foreground" : "bg-secondary border",
                    )}
                  >
                    {isUser ? (
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                        {assistantText}
                      </ReactMarkdown>
                    )}
                  </motion.div>
                  {!isUser && actionsToShow.map((action) => (
                    <ActionApprovalCard
                      key={action.id}
                      action={action}
                      loading={actionLoading === action.id}
                      onApprove={async (id) => {
                        setActionLoading(id);
                        try {
                          await onApproveAction(id);
                        } catch {
                          // Parent surfaces errors; avoid unhandled rejection in the button handler.
                        } finally {
                          setActionLoading(null);
                        }
                      }}
                      onReject={async (id) => {
                        setActionLoading(id);
                        try {
                          await onRejectAction(id);
                        } catch {
                          // Parent surfaces errors; avoid unhandled rejection in the button handler.
                        } finally {
                          setActionLoading(null);
                        }
                      }}
                    />
                  ))}
                  {!isUser && citations.length > 0 && (
                    <SourcesList citations={citations} />
                  )}
                </div>
                {isUser && (
                  <motion.div
                    whileHover={{ scale: 1.04 }}
                    className="shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center"
                  >
                    <User className="w-5 h-5 text-primary-foreground" />
                  </motion.div>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
        <motion.div ref={endRef} layout />
      </motion.div>

      <form onSubmit={handleSubmit} className="px-6 py-4 border-t bg-secondary/30">
        <div className="flex gap-3">
          <MentionComposer
            value={input}
            onChange={setInput}
            onSubmit={() => void handleSubmit({ preventDefault: () => {} } as React.FormEvent)}
            disabled={loading}
            placeholder="Ask a question… type @ for channels, Jira, GitHub"
          />
          <Button type="submit" disabled={loading || !input.trim()} className="shrink-0 self-end">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </Button>
        </div>
      </form>
    </motion.div>
  );
}
