"use client";

import * as React from "react";
import Link from "next/link";
import { Activity, Brain, Database, Network, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import type { GraphStatus, HealthReady, KnowledgeStatus, LlmStatus } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MetricGrid, SOURCE_COLORS, SOURCE_ENTITY_LABELS, SOURCE_ICONS, type MetricCardData } from "@/components/metric-grid";

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <Badge className={ok ? "bg-emerald-950 text-emerald-300 border-emerald-800" : "bg-rose-950 text-rose-300 border-rose-800"}>
      {ok ? "Healthy" : "Down"}
    </Badge>
  );
}

export default function DashboardPage() {
  const [knowledge, setKnowledge] = React.useState<KnowledgeStatus | null>(null);
  const [health, setHealth] = React.useState<HealthReady | null>(null);
  const [llm, setLlm] = React.useState<LlmStatus | null>(null);
  const [graph, setGraph] = React.useState<GraphStatus | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    Promise.all([
      api.knowledgeStatus(),
      api.healthReady().catch(() => null),
      api.llmStatus().catch(() => null),
      api.graphStatus().catch(() => null),
    ])
      .then(([k, h, l, g]) => {
        setKnowledge(k);
        setHealth(h);
        setLlm(l);
        setGraph(g);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const metrics: MetricCardData[] = knowledge
    ? [
        { id: "jira", source: "Jira", icon: SOURCE_ICONS.jira, entityCount: knowledge.jira_entities, entityLabel: SOURCE_ENTITY_LABELS.jira, status: knowledge.jira_configured ? "connected" : "disconnected", color: SOURCE_COLORS.jira },
        { id: "confluence", source: "Confluence", icon: SOURCE_ICONS.confluence, entityCount: knowledge.confluence_entities, entityLabel: SOURCE_ENTITY_LABELS.confluence, status: knowledge.confluence_configured ? "connected" : "disconnected", color: SOURCE_COLORS.confluence },
        { id: "github", source: "GitHub", icon: SOURCE_ICONS.github, entityCount: knowledge.github_entities, entityLabel: SOURCE_ENTITY_LABELS.github, status: knowledge.github_configured ? "connected" : "disconnected", color: SOURCE_COLORS.github },
        { id: "slack", source: "Slack", icon: SOURCE_ICONS.slack, entityCount: knowledge.slack_entities, entityLabel: SOURCE_ENTITY_LABELS.slack, status: knowledge.slack_configured ? "connected" : "disconnected", color: SOURCE_COLORS.slack },
        { id: "meetings", source: "Meetings", icon: SOURCE_ICONS.meetings, entityCount: knowledge.meetings_entities, entityLabel: SOURCE_ENTITY_LABELS.meetings, status: knowledge.meetings_configured ? "connected" : "disconnected", color: SOURCE_COLORS.meetings },
      ]
    : [];

  return (
    <div className="space-y-10">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Enterprise knowledge plane — {knowledge?.total_entities.toLocaleString() ?? "…"} indexed entities
          </p>
        </div>
        <Button asChild>
          <Link href="/chat">
            Open Chat <ArrowRight className="w-4 h-4" />
          </Link>
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          API unreachable: {error}. Ensure the backend is running at {api.baseUrl}.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2"><Database className="w-4 h-4" /> Postgres</CardDescription>
            <CardTitle className="text-lg flex items-center justify-between">
              Database <StatusBadge ok={health?.checks?.postgres?.status === "up"} />
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2"><Activity className="w-4 h-4" /> Redis</CardDescription>
            <CardTitle className="text-lg flex items-center justify-between">
              Cache <StatusBadge ok={health?.checks?.redis?.status === "up"} />
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2"><Network className="w-4 h-4" /> Neo4j</CardDescription>
            <CardTitle className="text-lg flex items-center justify-between">
              Graph <StatusBadge ok={graph?.connection?.status === "up"} />
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2"><Brain className="w-4 h-4" /> LLM</CardDescription>
            <CardTitle className="text-lg flex items-center justify-between">
              {llm?.configured[0] ?? "—"}
              <Badge variant="outline">{llm?.configured.length ?? 0} providers</Badge>
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <MetricGrid
        title="Knowledge Sources"
        description="Indexed content from connected enterprise systems"
        metrics={metrics}
      />

      <Card>
        <CardHeader>
          <CardTitle>Platform Phases</CardTitle>
          <CardDescription>Active capabilities in your deployment</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge>Phase 1 — Jira Q&A</Badge>
          <Badge>Phase 2 — Multi-source</Badge>
          <Badge>Phase {knowledge?.graph_phase ?? 3} — GraphRAG</Badge>
          <Badge>Phase {knowledge?.actions_phase ?? 4} — Actions</Badge>
          <Badge>Phase {knowledge?.meetings_phase ?? 5} — Meetings</Badge>
          {knowledge?.actions_enabled && <Badge variant="outline">Actions enabled</Badge>}
        </CardContent>
      </Card>
    </div>
  );
}
