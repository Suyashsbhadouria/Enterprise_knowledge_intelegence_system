"use client";

import * as React from "react";
import { Upload, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { KnowledgeStatus } from "@/lib/types";
import { MetricGrid, SOURCE_COLORS, SOURCE_ENTITY_LABELS, SOURCE_ICONS, type MetricCardData } from "@/components/metric-grid";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type SourceId = "jira" | "confluence" | "github" | "slack" | "meetings";

const SYNC_HANDLERS: Record<SourceId, () => Promise<unknown>> = {
  jira: () => api.syncJira(),
  confluence: () => api.syncConfluence(),
  github: () => api.syncGitHub(),
  slack: () => api.syncSlack(),
  meetings: () => api.syncMeetings(),
};

export default function KnowledgePage() {
  const [status, setStatus] = React.useState<KnowledgeStatus | null>(null);
  const [syncing, setSyncing] = React.useState<Set<string>>(new Set());
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const refresh = React.useCallback(async () => {
    try {
      const data = await api.knowledgeStatus();
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load status");
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const buildMetrics = (): MetricCardData[] => {
    if (!status) return [];
    const configured: Record<SourceId, boolean> = {
      jira: status.jira_configured,
      confluence: status.confluence_configured,
      github: status.github_configured,
      slack: status.slack_configured,
      meetings: status.meetings_configured,
    };
    const entities: Record<SourceId, number> = {
      jira: status.jira_entities,
      confluence: status.confluence_entities,
      github: status.github_entities,
      slack: status.slack_entities,
      meetings: status.meetings_entities,
    };
    const labels: Record<SourceId, string> = {
      jira: "Jira",
      confluence: "Confluence",
      github: "GitHub",
      slack: "Slack",
      meetings: "Meetings",
    };

    return (Object.keys(labels) as SourceId[]).map((id) => ({
      id,
      source: labels[id],
      icon: SOURCE_ICONS[id],
      entityCount: entities[id],
      entityLabel: SOURCE_ENTITY_LABELS[id],
      color: SOURCE_COLORS[id],
      status: syncing.has(id) ? "syncing" : configured[id] ? "connected" : "disconnected",
      lastSync: configured[id] ? "Configured" : "Not configured in .env",
    }));
  };

  const handleSync = async (id: string) => {
    const source = id as SourceId;
    setSyncing((prev) => new Set(prev).add(id));
    setMessage(null);
    setError(null);
    try {
      const result = await SYNC_HANDLERS[source]();
      setMessage(`${source} sync complete: ${JSON.stringify(result)}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Sync failed for ${source}`);
    } finally {
      setSyncing((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const result = await api.uploadMeeting(file);
      setMessage(`Uploaded ${file.name}: ${JSON.stringify(result)}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Knowledge</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Sync and index content from Jira, Confluence, GitHub, Slack, and meeting transcripts.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">{message}</div>
      )}

      {!status ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <MetricGrid metrics={buildMetrics()} onSync={handleSync} />
      )}

      <Card>
        <CardHeader>
          <CardTitle>Upload meeting transcript</CardTitle>
          <CardDescription>.vtt, .srt, .txt, or .md — UTF-8 text files</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-4">
          <Input
            ref={fileRef}
            type="file"
            accept=".vtt,.srt,.txt,.md"
            className="max-w-sm"
            onChange={handleUpload}
            disabled={uploading}
          />
          <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Upload className="w-4 h-4 mr-2" />
            )}
            Choose file
          </Button>
          {status?.meetings_transcripts_dir && (
            <p className="text-xs text-muted-foreground w-full">
              Directory: {status.meetings_transcripts_dir}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
