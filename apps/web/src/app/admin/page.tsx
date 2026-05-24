"use client";

import * as React from "react";
import { Loader2, Database, Rocket, Building2 } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function AdminPage() {
  const [loading, setLoading] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const run = async (key: string, fn: () => Promise<Record<string, unknown>>) => {
    setLoading(key);
    setError(null);
    setResult(null);
    try {
      const data = await fn();
      setResult(JSON.stringify(data, null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Admin</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Development-only operations. Requires <code className="text-xs">APP_ENV=development</code> on the API.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="w-5 h-5" /> Seed tenant
            </CardTitle>
            <CardDescription>Index real Jira + Confluence and build Neo4j graph</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              className="w-full"
              onClick={() => run("seed", api.seed)}
              disabled={loading !== null}
            >
              {loading === "seed" ? <Loader2 className="w-4 h-4 animate-spin" /> : "POST /admin/seed"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Building2 className="w-5 h-5" /> Nexus fixture
            </CardTitle>
            <CardDescription>Load Nexus Dynamics demo data (no live APIs)</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              className="w-full"
              variant="secondary"
              onClick={() => run("enterprise", () => api.seedEnterprise(true))}
              disabled={loading !== null}
            >
              {loading === "enterprise" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                "POST /admin/seed-enterprise"
              )}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Rocket className="w-5 h-5" /> Publish live
            </CardTitle>
            <CardDescription>Create Nexus content in your real Jira, Confluence, Slack</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button
              className="w-full"
              variant="outline"
              onClick={() => run("dry", () => api.publishEnterprise(true))}
              disabled={loading !== null}
            >
              {loading === "dry" ? <Loader2 className="w-4 h-4 animate-spin" /> : "Dry run"}
            </Button>
            <Button
              className="w-full"
              variant="destructive"
              onClick={() => run("publish", () => api.publishEnterprise(false))}
              disabled={loading !== null}
            >
              {loading === "publish" ? <Loader2 className="w-4 h-4 animate-spin" /> : "Publish"}
            </Button>
          </CardContent>
        </Card>
      </div>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Response</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs overflow-auto max-h-96 p-4 rounded-lg bg-secondary font-mono">
              {result}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
