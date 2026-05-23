from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from ekcip_api.db.session import close_db, init_db
from ekcip_api.exceptions import register_exception_handlers
from ekcip_api.middleware.trace import TraceIdMiddleware
from ekcip_api.routes import admin, connectors, conversations, graph, health, knowledge, llm
from ekcip_connectors.factory import build_runtime_connectors
from ekcip_connectors.mcp_registry import get_mcp_registry
from ekcip_graph.client import verify_neo4j_connection
from ekcip_llm.factory import build_llm_router
from ekcip_shared.config import get_settings
from ekcip_shared.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    warnings = settings.validate_startup()
    for warning in warnings:
        logger.warning("startup_config", warning=warning)

    await init_db()
    app.state.settings = settings
    app.state.connectors = build_runtime_connectors(settings)
    app.state.mcp_registry = get_mcp_registry(
        atlassian_server=settings.mcp_server_atlassian,
        github_server=settings.mcp_server_github,
        slack_server=settings.mcp_server_slack,
        neon_server=settings.mcp_server_neon,
    )
    app.state.llm_router = build_llm_router(settings)
    if settings.neo4j_configured:
        neo4j_status = await verify_neo4j_connection(settings)
        logger.info("neo4j_startup_check", **neo4j_status)
    else:
        logger.warning("neo4j_not_configured", hint="Set NEO4J_URI and NEO4J_PASSWORD for Aura")
    logger.info("ekcip_started", env=settings.app_env)
    yield
    await close_db()
    logger.info("ekcip_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    dev_auth_note = (
        "\n\n**Development auth:** With `APP_ENV=development` and empty `API_KEY`, "
        "conversation endpoints work without credentials in Swagger."
    )
    prod_auth_note = (
        "\n\n**API auth:** Send `X-API-Key: <API_KEY>` or `Authorization: Bearer <API_KEY>`."
    )
    application = FastAPI(
        title="EKCIP API",
        version="0.1.0",
        description=(
            "Enterprise Knowledge & Coordination Intelligence Platform"
            + (dev_auth_note if settings.app_env == "development" and not settings.api_key else prod_auth_note)
        ),
        lifespan=lifespan,
    )

    if settings.api_key:

        def custom_openapi():
            if application.openapi_schema:
                return application.openapi_schema
            schema = get_openapi(
                title=application.title,
                version=application.version,
                description=application.description,
                routes=application.routes,
            )
            schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            }
            for path_item in schema.get("paths", {}).values():
                for operation in path_item.values():
                    if operation.get("tags") == ["conversations"]:
                        operation["security"] = [{"ApiKeyAuth": []}]
            application.openapi_schema = schema
            return application.openapi_schema

        application.openapi = custom_openapi

    application.add_middleware(TraceIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=bool(settings.cors_origin_list),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Trace-Id"],
    )

    register_exception_handlers(application)
    application.include_router(health.router, tags=["health"])
    application.include_router(connectors.router, prefix="/v1/connectors", tags=["connectors"])
    application.include_router(conversations.router, prefix="/v1/conversations", tags=["conversations"])
    application.include_router(llm.router, prefix="/v1/llm", tags=["llm"])
    application.include_router(graph.router, prefix="/v1/graph", tags=["graph"])
    application.include_router(knowledge.router, prefix="/v1/knowledge", tags=["knowledge"])
    if settings.app_env == "development":
        application.include_router(admin.router, prefix="/v1/admin", tags=["admin"])
    return application
