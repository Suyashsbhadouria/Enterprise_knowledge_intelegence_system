"use client";

import * as React from "react";
import Link from "next/link";
import { Check, X, Loader2, MessageSquare } from "lucide-react";
import { api } from "@/lib/api";
import { isActionAwaitingApproval } from "@/lib/chat-actions";
import { useConversation } from "@/providers/conversation-provider";
import type { ProposedAction } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export default function ActionsPage() {
  const { conversationId } = useConversation();
  const [actions, setActions] = React.useState<ProposedAction[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!conversationId) {
      setActions([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const result = await api.listActions(conversationId);
      setActions(result.actions);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load actions");
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  React.useEffect(() => {
    load();
  }, [load]);

  const handleApprove = async (id: string) => {
    setBusyId(id);
    try {
      await api.approveAction(id, true);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approve failed");
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (id: string) => {
    setBusyId(id);
    try {
      await api.rejectAction(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reject failed");
    } finally {
      setBusyId(null);
    }
  };

  const pending = actions.filter((a) => isActionAwaitingApproval(a.status));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Actions</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Approval queue for Slack, Jira, and scheduled actions (Phase 4).
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/chat">
            <MessageSquare className="w-4 h-4 mr-1" /> Open chat
          </Link>
        </Button>
      </div>

      {!conversationId && (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            Start a <Link href="/chat" className="text-primary hover:underline">chat thread</Link> to propose actions.
          </CardContent>
        </Card>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          <div className="flex gap-2">
            <Badge>{pending.length} pending</Badge>
            <Badge variant="outline">{actions.length} total</Badge>
          </div>

          <div className="space-y-4">
            {actions.length === 0 && conversationId && (
              <Card>
                <CardContent className="py-8 text-center text-muted-foreground text-sm">
                  No actions yet. Ask the assistant to send a Slack message or add a Jira comment.
                </CardContent>
              </Card>
            )}
            {actions.map((action) => (
              <Card key={action.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between gap-2">
                    <CardTitle className="text-base">{action.action_type}</CardTitle>
                    <Badge
                      className={
                        isActionAwaitingApproval(action.status)
                          ? "bg-amber-950 text-amber-300"
                          : action.status === "executed"
                            ? "bg-emerald-950 text-emerald-300"
                            : ""
                      }
                    >
                      {action.status}
                    </Badge>
                  </div>
                  <CardDescription>{new Date(action.created_at).toLocaleString()}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm">{action.preview}</p>
                  {action.rationale && (
                    <p className="text-xs text-muted-foreground">{action.rationale}</p>
                  )}
                  {action.error && (
                    <p className="text-xs text-destructive">{action.error}</p>
                  )}
                  {isActionAwaitingApproval(action.status) && (
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => handleApprove(action.id)} disabled={busyId === action.id}>
                        {busyId === action.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Check className="w-4 h-4 mr-1" />
                        )}
                        Approve & execute
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleReject(action.id)}
                        disabled={busyId === action.id}
                      >
                        <X className="w-4 h-4 mr-1" /> Reject
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
