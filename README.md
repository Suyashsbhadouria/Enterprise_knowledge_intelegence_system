# EKCIP — Enterprise Knowledge & Coordination Intelligence Platform

Phase 0 foundation, **Phase 1** Jira Q&A, **Phase 2** multi-source read, **Phase 3** GraphRAG, and **Phase 4** approval-aware actions (Slack post/schedule, Jira comment/status) with human gate before execution.

## Prerequisites

- Python 3.11+
- Docker Desktop (Postgres + Redis only)
- [Neo4j Aura](https://console.neo4j.io) free instance (graph database)

## Neo4j Aura setup

1. Create an instance at https://console.neo4j.io  
2. Download the credentials file from **Connect** (or copy values from the console).
3. Map Aura’s names to `.env` (`NEO4J_USERNAME` → `NEO4J_USER`):

```env
NEO4J_URI=neo4j+ssc://xxxxxxxx.databases.neo4j.io
NEO4J_USER=xxxxxxxx
NEO4J_PASSWORD=your-aura-password
NEO4J_DATABASE=xxxxxxxx
```

On Windows, if the console gives `neo4j+s://` and you see **Unable to retrieve routing information**, change the scheme to `neo4j+ssc://` (or keep `neo4j+s://` — the API auto-upgrades it for Aura). Username and database are your **instance id**, not `neo4j`.

4. Verify after starting the API: `GET http://127.0.0.1:8000/v1/graph/status`

Local Docker Neo4j is **optional** only if you need it: `docker compose --profile local-neo4j up -d neo4j`

## Quick start

```powershell
cd "c:\Users\Relanto\Desktop\Python\Enterprise knowledge intellligence platform - PranayV2"
copy .env.example .env
# Edit .env: Aura NEO4J_* + LLM keys

.\scripts\start-api.ps1
```

Or manually:

```powershell
.\scripts\start-infra.ps1
alembic upgrade head
uvicorn ekcip_api.main:app --reload --port 8000
```

| Service  | Where |
|----------|--------|
| Postgres | `localhost:5433` (Docker; avoids Windows PostgreSQL on 5432) |
| Redis    | `localhost:6379` (Docker) |
| Neo4j    | **Neo4j Aura** (cloud, from `.env`) |

Open http://127.0.0.1:8000/docs

## LLM providers (no OpenAI)

Chat uses: **Grok → NVIDIA → Hugging Face → Gemini** (see `.env.example`).  
Status: `GET /v1/llm/status`

## MCP & Cursor plugins

| Source | Cursor MCP server ID |
|--------|----------------------|
| Jira / Confluence | `plugin-atlassian-atlassian` |
| GitHub | `user-github` |
| Slack | `plugin-slack-slack` |

`GET /v1/connectors/mcp` — registry for agent tooling.

## Phase 1: Jira knowledge Q&A

1. Set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`. Embeddings default to **local** (`sentence-transformers/all-MiniLM-L6-v2`, downloaded on first sync). Cloud fallbacks: `nvidia`, `huggingface`, `gemini`.
2. Sync issues: `POST /v1/knowledge/jira/sync` — JQL must be **bounded** (e.g. `updated >= -90d ORDER BY updated DESC` or `project = PROJ ORDER BY updated DESC`).
3. **Index your tenant:** In development run `POST /v1/admin/seed` (syncs **real** Jira issues + Confluence pages, builds Neo4j graph, returns `sample_queries`) or `.\scripts\seed-test-data.ps1`.
4. Chat: `POST /v1/conversations/{id}/messages` — answers use indexed knowledge with **citations**.

## Phase 2: Confluence (read-only)

Uses the same Atlassian email + API token as Jira. Set `CONFLUENCE_BASE_URL` or rely on `JIRA_BASE_URL/wiki` auto-detection.

1. Sync pages: `POST /v1/knowledge/confluence/sync` — CQL must be **bounded** (default: `type=page AND lastModified >= now("-90d") order by lastModified desc`).
2. Status: `GET /v1/knowledge/status` — returns `jira_chunks`, `confluence_chunks`, and `total_chunks`.
3. Chat searches **both** Jira and Confluence; cite page titles and issue keys from indexed content.

### GitHub (read-only)

1. Set `GITHUB_TOKEN` and `GITHUB_REPOS=owner/repo,owner/other` (explicit bounded list).
2. Sync: `POST /v1/knowledge/github/sync` — issues, PRs, and **commits** updated within `GITHUB_SYNC_DAYS` (default 90).
3. Chat cites items like `acme/app#42` (issues), `acme/app!7` (PRs), and `acme/app@a1b2c3d` (commits with message + push time).

### Slack (read-only)

1. Invite the bot to channels, then set `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_IDS=C01234567,...`.
2. **Bot token scopes** (api.slack.com → your app → OAuth & Permissions → Bot Token Scopes):

   `channels:history`, `channels:read`, `groups:history`, `groups:read`

   After adding scopes, **Reinstall to Workspace** and paste the new `xoxb-` token into `.env`.
3. Sync: `POST /v1/knowledge/slack/sync` — channel history within `SLACK_SYNC_DAYS` (default 30).
3. Chat searches indexed messages alongside Jira, Confluence, and GitHub.

## Phase 3: GraphRAG + coordination intelligence

Requires Neo4j populated via `POST /v1/admin/seed` (enterprise graph from real Jira + Confluence).

1. Chat uses **vector chunks** plus **Neo4j Cypher** (assignees, project rollups, blocker scan).
2. LangGraph adds an **analyze** step for blocker summaries when relevant.
3. Response `phase` is `3-qa`; graph query modes appear in orchestration metadata.
4. `GET /v1/knowledge/status` includes `neo4j_status` and `graph_phase`.

**Example questions:** “Who is assigned to SCRUM-12?”, “Summarize all issues in project SCRUM”, “What blockers exist in project ENG?”

## Phase 4: Approval-aware action plane

Actions are **proposed** from chat, stored in Postgres, and **never execute** until approved.

1. Ask with an action intent, e.g. `Send a Slack message to C01234567 saying "Can you confirm the rollout time?"` or `Add a comment on SCRUM-12 saying blocked on auth`.
2. Chat response includes `proposed_actions[]` with previews (`phase`: `4-qa-proposed` when actions are drafted).
3. List pending actions: `GET /v1/actions/conversations/{conversation_id}/actions`
4. Approve (optionally execute): `POST /v1/actions/{action_id}/approve` with `{"execute": true}`
5. Reject: `POST /v1/actions/{action_id}/reject`

| Action | Connector | Notes |
|--------|-----------|--------|
| `send_slack_message` | Slack `chat.postMessage` | Channel must be in `SLACK_CHANNEL_IDS` |
| `schedule_slack_message` | Slack `chat.scheduleMessage` | Requires `chat:write` scope |
| `add_jira_comment` | Jira REST | Uses same credentials as sync |
| `update_issue_status` | Jira transitions API | Matches status name to available transition |
| `create_reminder` | Slack schedule (if configured) | Otherwise stored as approved metadata |

**Slack write scopes:** add `chat:write` to the bot, reinstall, update `SLACK_BOT_TOKEN`.

```env
ACTIONS_ENABLED=true
ACTIONS_REQUIRE_APPROVAL=true
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | Postgres, Redis, Aura Neo4j |
| GET | `/v1/graph/status` | Aura connection check |
| GET | `/v1/llm/status` | LLM provider config |
| GET | `/v1/knowledge/status` | Indexed chunk counts (Jira + Confluence) |
| POST | `/v1/knowledge/jira/sync` | Index Jira issues (read + embed) |
| POST | `/v1/knowledge/confluence/sync` | Index Confluence pages (read + embed) |
| POST | `/v1/knowledge/github/sync` | Index GitHub issues, PRs, and commits (read + embed) |
| POST | `/v1/knowledge/slack/sync` | Index Slack channel messages (read + embed) |
| POST | `/v1/conversations` | Create thread |
| POST | `/v1/conversations/{id}/messages` | RAG chat with citations and optional `proposed_actions` |
| GET | `/v1/actions/conversations/{id}/actions` | List proposed/approved actions for a thread |
| POST | `/v1/actions/{action_id}/approve` | Approve (and optionally execute) a proposed action |
| POST | `/v1/actions/{action_id}/reject` | Reject a proposed action |

## Tests

```powershell
pip install -e ".[dev]"
pytest tests/ -q
```
