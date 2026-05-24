"use client";

import * as React from "react";
import { Save } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const API_KEY_STORAGE = "ekcip_api_key";

export default function SettingsPage() {
  const apiUrl = api.baseUrl;
  const [apiKey, setApiKey] = React.useState("");
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    setApiKey(localStorage.getItem(API_KEY_STORAGE) ?? "");
  }, []);

  const handleSave = () => {
    if (apiKey.trim()) {
      localStorage.setItem(API_KEY_STORAGE, apiKey.trim());
    } else {
      localStorage.removeItem(API_KEY_STORAGE);
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Connection and authentication for the EKCIP API.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>API connection</CardTitle>
          <CardDescription>
            Backend URL is set via <code className="text-xs">NEXT_PUBLIC_API_URL</code> at build time.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-1.5 block">API URL</label>
            <Input value={apiUrl} readOnly className="font-mono text-sm" />
          </div>
          <div>
            <label className="text-sm font-medium mb-1.5 block">API key (optional in dev)</label>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="X-API-Key or Bearer token"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground mt-1.5">
              Sent as <code className="text-xs">X-API-Key</code> header. Leave empty when{" "}
              <code className="text-xs">APP_ENV=development</code> and no API_KEY is set.
            </p>
          </div>
          <Button onClick={handleSave}>
            <Save className="w-4 h-4 mr-2" />
            {saved ? "Saved" : "Save"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
