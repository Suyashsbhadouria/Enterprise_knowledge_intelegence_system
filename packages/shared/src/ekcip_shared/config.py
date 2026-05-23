from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    api_key: str | None = None

    database_url: str = "postgresql+asyncpg://ekcip:ekcip@localhost:5433/ekcip"
    redis_url: str = "redis://localhost:6379/0"
    # Neo4j Aura: neo4j+ssc://<id>.databases.neo4j.io (from https://console.neo4j.io)
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None
    neo4j_database: str = "neo4j"

    # LLM fallback chain: grok → nvidia → huggingface → gemini (no OpenAI)
    llm_provider_order: str = "grok,nvidia,huggingface,gemini"
    xai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("XAI_API_KEY", "GROK_API_KEY"),
    )
    nvidia_api_key: str | None = None
    huggingface_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("HUGGINGFACE_API_KEY", "HF_TOKEN"),
    )
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    grok_model: str = "grok-3-mini"
    nvidia_model: str = "meta/llama-3.1-8b-instruct"
    huggingface_model: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    gemini_model: str = "gemini-2.0-flash"

    # Embeddings: local sentence-transformers first (no API/DNS), then cloud fallbacks
    embedding_provider_order: str = "local,nvidia,huggingface,gemini"
    local_embeddings_enabled: bool = True
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    local_embedding_device: str = "cpu"
    nvidia_embedding_model: str = "nvidia/nv-embedqa-e5-v5"
    gemini_embedding_model: str = "text-embedding-004"
    huggingface_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    knowledge_top_k: int = 5
    jira_sync_jql: str = "updated >= -90d ORDER BY updated DESC"
    confluence_sync_cql: str = (
        'type=page AND lastModified >= now("-90d") order by lastModified desc'
    )

    # Phase 2 GitHub (bounded: explicit owner/repo list)
    github_repos: str = ""
    github_sync_days: int = 90
    github_max_results_per_repo: int = 50
    github_max_commits_per_repo: int = 50

    # Phase 2 Slack read (bounded: explicit channel IDs)
    slack_channel_ids: str = ""
    slack_sync_days: int = 30
    slack_max_messages_per_channel: int = 100

    # Enterprise dev seed: sync real tenant data (no fake Jira issues)
    seed_jira_project_keys: str = ""
    seed_jira_days: int = 90
    seed_max_results_per_project: int = 50
    seed_max_projects: int = 20
    seed_confluence_space_keys: str = ""
    seed_max_confluence_spaces: int = 10

    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    confluence_base_url: str | None = None
    github_token: str | None = None
    slack_bot_token: str | None = None

    mcp_server_atlassian: str = "plugin-atlassian-atlassian"
    mcp_server_github: str = "user-github"
    mcp_server_slack: str = "plugin-slack-slack"
    mcp_server_neon: str = "plugin-neon-postgres-neon"

    @model_validator(mode="before")
    @classmethod
    def map_aura_env_aliases(cls, data: object) -> object:
        """Aura download files use NEO4J_USERNAME; map to neo4j_user when NEO4J_USER omitted."""
        if not isinstance(data, dict):
            return data
        if data.get("neo4j_user") in (None, "", "neo4j") and data.get("NEO4J_USER") in (None, ""):
            username = data.get("NEO4J_USERNAME")
            if username:
                data = {**data, "neo4j_user": username}
        return data

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors(cls, value: str | list[str]) -> str:
        if isinstance(value, list):
            return ",".join(value)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def neo4j_configured(self) -> bool:
        return bool(self.neo4j_uri.strip() and self.neo4j_password)

    @property
    def neo4j_is_aura(self) -> bool:
        uri = self.neo4j_uri.lower()
        return (
            uri.startswith("neo4j+s://")
            or uri.startswith("neo4j+ssc://")
            or "databases.neo4j.io" in uri
        )

    @property
    def neo4j_driver_uri(self) -> str:
        """Aura URI for the driver; neo4j+s often fails TLS verify on Windows."""
        uri = self.neo4j_uri.strip()
        if self.neo4j_is_aura and uri.lower().startswith("neo4j+s://"):
            return "neo4j+ssc://" + uri[len("neo4j+s://") :]
        return uri

    def validate_startup(self) -> list[str]:
        """Return warnings for missing optional config; raise only on hard failures."""
        warnings: list[str] = []
        if self.app_env == "production" and not self.api_key:
            raise ValueError("API_KEY is required in production")
        if not any(
            (
                self.xai_api_key,
                self.nvidia_api_key,
                self.huggingface_api_key,
                self.gemini_api_key,
            )
        ):
            warnings.append(
                "No LLM API keys set (XAI_API_KEY, NVIDIA_API_KEY, HUGGINGFACE_API_KEY, GEMINI_API_KEY)"
            )
        if self.neo4j_uri.strip() and not self.neo4j_password:
            warnings.append("NEO4J_URI is set but NEO4J_PASSWORD is missing (Aura credentials)")
        if self.app_env == "production" and not self.neo4j_configured:
            warnings.append("Neo4j Aura not configured (NEO4J_URI + NEO4J_PASSWORD)")
        return warnings

    def has_llm_provider(self) -> bool:
        return bool(
            self.xai_api_key
            or self.nvidia_api_key
            or self.huggingface_api_key
            or self.gemini_api_key
        )

    @property
    def jira_configured(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)

    @property
    def confluence_wiki_base_url(self) -> str | None:
        if self.confluence_base_url and self.confluence_base_url.strip():
            return self.confluence_base_url.strip()
        if self.jira_base_url and self.jira_base_url.strip():
            return f"{self.jira_base_url.strip().rstrip('/')}/wiki"
        return None

    @property
    def confluence_configured(self) -> bool:
        return bool(
            self.confluence_wiki_base_url and self.jira_email and self.jira_api_token
        )

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token and self.github_repos.strip())

    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_bot_token and self.slack_channel_ids.strip())


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_startup()
    return settings
