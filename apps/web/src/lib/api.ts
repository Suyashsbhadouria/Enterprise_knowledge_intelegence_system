import type {
  ApiEnvelope,
  AssistantReply,
  Conversation,
  ConversationDetail,
  GraphStatus,
  HealthReady,
  KnowledgeStatus,
  LlmStatus,
  MentionSuggestResponse,
  ProposedAction,
  SyncResult,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ekcip_api_key");
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const apiKey = getApiKey();
  if (apiKey) {
    headers.set("X-API-Key", apiKey);
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const envelope: ApiEnvelope<T> = await response.json();

  if (!response.ok || !envelope.success) {
    throw new Error(envelope.error ?? `Request failed (${response.status})`);
  }
  if (envelope.data === null) {
    throw new Error("Empty response from API");
  }
  return envelope.data;
}

export const api = {
  baseUrl: API_BASE,

  healthLive: () => request<{ status: string }>("/health/live"),
  healthReady: () => request<HealthReady>("/health/ready"),

  knowledgeStatus: () => request<KnowledgeStatus>("/v1/knowledge/status"),
  syncJira: () => request<SyncResult>("/v1/knowledge/jira/sync", { method: "POST", body: "{}" }),
  syncConfluence: () =>
    request<SyncResult>("/v1/knowledge/confluence/sync", { method: "POST", body: "{}" }),
  syncGitHub: () => request<SyncResult>("/v1/knowledge/github/sync", { method: "POST", body: "{}" }),
  syncSlack: () => request<SyncResult>("/v1/knowledge/slack/sync", { method: "POST", body: "{}" }),
  syncMeetings: () =>
    request<SyncResult>("/v1/knowledge/meetings/sync", { method: "POST", body: "{}" }),
  uploadMeeting: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<SyncResult>("/v1/knowledge/meetings/upload", { method: "POST", body: form });
  },

  llmStatus: () => request<LlmStatus>("/v1/llm/status"),
  graphStatus: () => request<GraphStatus>("/v1/graph/status"),

  createConversation: (title?: string) =>
    request<Conversation>("/v1/conversations", {
      method: "POST",
      body: JSON.stringify({ title: title ?? null }),
    }),
  getConversation: (id: string) => request<ConversationDetail>(`/v1/conversations/${id}`),
  postMessage: (conversationId: string, content: string) =>
    request<AssistantReply>(`/v1/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  mentionSuggest: (q: string, limit = 25) => {
    const params = new URLSearchParams({ q, limit: String(limit) });
    return request<MentionSuggestResponse>(`/v1/mentions/suggest?${params}`);
  },

  listActions: (conversationId: string) =>
    request<{ actions: ProposedAction[] }>(`/v1/actions/conversations/${conversationId}/actions`),
  approveAction: (actionId: string, execute = true) =>
    request<ProposedAction>(`/v1/actions/${actionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ execute }),
    }),
  rejectAction: (actionId: string, reason?: string) =>
    request<ProposedAction>(`/v1/actions/${actionId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),

  seed: () => request<Record<string, unknown>>("/v1/admin/seed", { method: "POST", body: "{}" }),
  seedEnterprise: (clearExisting = true) =>
    request<Record<string, unknown>>("/v1/admin/seed-enterprise", {
      method: "POST",
      body: JSON.stringify({ clear_existing: clearExisting }),
    }),
  publishEnterprise: (dryRun = false) =>
    request<Record<string, unknown>>("/v1/admin/publish-enterprise", {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun }),
    }),
};
