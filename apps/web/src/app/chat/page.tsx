"use client";

import * as React from "react";
import { Plus, Loader2 } from "lucide-react";
import { ChatInterface } from "@/components/chat-interface";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  attachActionsBelowAssistantReplies,
  enrichMessage,
  type ChatMessage,
} from "@/lib/chat-actions";
import { useConversation } from "@/providers/conversation-provider";
import type { Citation, ProposedAction } from "@/lib/types";

function mergeMessageMeta(
  messages: ChatMessage[],
  meta: Record<string, { citations?: Citation[] }>,
): ChatMessage[] {
  return messages.map((message) =>
    enrichMessage({
      ...message,
      citations: meta[message.id]?.citations ?? message.citations,
    }),
  );
}

export default function ChatPage() {
  const { conversationId, setConversationId } = useConversation();
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [initLoading, setInitLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [replyMeta, setReplyMeta] = React.useState<
    Record<string, { citations?: Citation[] }>
  >({});

  React.useEffect(() => {
    let cancelled = false;

    async function init() {
      setInitLoading(true);
      setError(null);
      try {
        let id = conversationId;
        if (!id) {
          const conv = await api.createConversation("New conversation");
          id = conv.id;
          setConversationId(id);
        }
        if (cancelled) return;

        const [detail, actionsResult] = await Promise.all([
          api.getConversation(id),
          api.listActions(id).catch(() => ({ actions: [] as ProposedAction[] })),
        ]);

        if (cancelled) return;
        setMessages(
          mergeMessageMeta(
            attachActionsBelowAssistantReplies(detail.messages, actionsResult.actions),
            replyMeta,
          ),
        );
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to initialize chat");
        }
      } finally {
        if (!cancelled) setInitLoading(false);
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, [conversationId, setConversationId]);

  const handleSend = async (content: string) => {
    if (!conversationId) return;
    setLoading(true);
    setError(null);

    const optimistic: ChatMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: conversationId,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const reply = await api.postMessage(conversationId, content);
      const nextMeta = {
        ...replyMeta,
        [reply.message.id]: {
          citations: reply.citations,
        },
      };
      setReplyMeta(nextMeta);

      const detail = await api.getConversation(conversationId);
      const actionsResult = await api.listActions(conversationId);

      setMessages(
        mergeMessageMeta(
          attachActionsBelowAssistantReplies(detail.messages, actionsResult.actions),
          nextMeta,
        ),
      );
    } catch (e) {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setError(e instanceof Error ? e.message : "Failed to send message");
    } finally {
      setLoading(false);
    }
  };

  const refreshActions = async () => {
    if (!conversationId) return;
    const [detail, actionsResult] = await Promise.all([
      api.getConversation(conversationId),
      api.listActions(conversationId),
    ]);
    setMessages(
      mergeMessageMeta(
        attachActionsBelowAssistantReplies(detail.messages, actionsResult.actions),
        replyMeta,
      ),
    );
  };

  const markActionUpdated = (updated: ProposedAction) => {
    setMessages((prev) =>
      prev.map((message) => {
        if (!message.proposedActions?.some((action) => action.id === updated.id)) {
          return message;
        }
        return {
          ...message,
          proposedActions: message.proposedActions.map((action) =>
            action.id === updated.id ? updated : action,
          ),
        };
      }),
    );
  };

  const handleApprove = async (actionId: string) => {
    setError(null);
    try {
      const updated = await api.approveAction(actionId, true);
      markActionUpdated(updated);
      await refreshActions();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Approve failed";
      if (message.includes("not pending") && message.includes("executed")) {
        await refreshActions();
        return;
      }
      setError(message);
      await refreshActions();
    }
  };

  const handleReject = async (actionId: string) => {
    setError(null);
    try {
      const updated = await api.rejectAction(actionId);
      markActionUpdated(updated);
      await refreshActions();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Reject failed";
      if (message.includes("not pending")) {
        await refreshActions();
        return;
      }
      setError(message);
      await refreshActions();
    }
  };

  const startNewConversation = async () => {
    setInitLoading(true);
    setReplyMeta({});
    try {
      const conv = await api.createConversation("New conversation");
      setConversationId(conv.id);
      setMessages([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create conversation");
    } finally {
      setInitLoading(false);
    }
  };

  if (initLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Chat</h1>
          <p className="text-sm text-muted-foreground">
            Ask questions with cited sources and approval-aware actions
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={startNewConversation}>
          <Plus className="w-4 h-4 mr-1" /> New thread
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <ChatInterface
        messages={messages}
        onSend={handleSend}
        onApproveAction={handleApprove}
        onRejectAction={handleReject}
        loading={loading}
      />
    </div>
  );
}
