export interface ApiMeta {
  page?: number | null;
  limit?: number | null;
  total?: number | null;
  trace_id?: string | null;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta: ApiMeta;
}

export interface Conversation {
  id: string;
  title: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface MentionSuggestion {
  kind: string;
  mention: string;
  label: string;
  description: string | null;
  resolved_text: string;
  metadata: Record<string, unknown>;
}

export interface MentionSuggestResponse {
  suggestions: MentionSuggestion[];
}

export interface Citation {
  source: string;
  source_id: string;
  title: string;
  url: string | null;
  excerpt: string;
  score: number;
}

export interface ProposedAction {
  id: string;
  conversation_id: string;
  triggering_message_id: string;
  action_type: string;
  payload: Record<string, unknown>;
  preview: string;
  rationale: string | null;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  executed_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
}

export interface AssistantReply {
  message: Message;
  phase: string;
  note: string;
  llm_provider: string | null;
  llm_model: string | null;
  citations: Citation[];
  proposed_actions: ProposedAction[];
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

export interface KnowledgeStatus {
  jira_entities: number;
  confluence_entities: number;
  github_entities: number;
  slack_entities: number;
  meetings_entities: number;
  total_entities: number;
  stats_synced_at: string | null;
  jira_configured: boolean;
  confluence_configured: boolean;
  github_configured: boolean;
  slack_configured: boolean;
  meetings_configured: boolean;
  neo4j_configured: boolean;
  neo4j_status: string | null;
  graph_phase: number;
  actions_phase: number;
  meetings_phase: number;
  actions_enabled: boolean;
  actions_require_approval: boolean;
  embedding_providers: string[];
  local_embedding_model: string;
  local_embeddings_enabled: boolean;
  meetings_transcripts_dir?: string | null;
}

export interface HealthCheck {
  status: string;
  message?: string;
}

export interface HealthReady {
  status: string;
  checks: {
    postgres: HealthCheck;
    redis: HealthCheck;
    neo4j: HealthCheck;
    connectors: HealthCheck | Record<string, unknown>;
  };
}

export interface LlmStatus {
  provider_order: string[];
  configured: string[];
  models: Record<string, string>;
}

export interface GraphStatus {
  configured: boolean;
  aura: boolean;
  database: string;
  connection: { status: string; message?: string };
}

export interface SyncResult {
  synced?: number;
  chunks?: number;
  [key: string]: unknown;
}
