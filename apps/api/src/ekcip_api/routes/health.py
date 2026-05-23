from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ekcip_api.db.session import get_engine
from ekcip_api.middleware.trace import get_trace_id
from ekcip_api.services import health as health_service
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


@router.get("/health/live")
async def liveness(request: Request) -> JSONResponse:
    envelope = ApiEnvelope.ok({"status": "alive"}, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    connectors = request.app.state.connectors

    postgres = await health_service.check_postgres(get_engine())
    redis_status = await health_service.check_redis(settings.redis_url)
    neo4j_status = await health_service.check_neo4j(settings)
    connector_status = await health_service.check_connectors(connectors)

    checks = {
        "postgres": postgres,
        "redis": redis_status,
        "neo4j": neo4j_status,
        "connectors": connector_status,
    }
    neo4j_required = settings.neo4j_configured
    neo4j_ok = neo4j_status.get("status") == "up" or (
        not neo4j_required and neo4j_status.get("status") == "skipped"
    )
    all_up = postgres.get("status") == "up" and redis_status.get("status") == "up" and neo4j_ok
    envelope = ApiEnvelope.ok(
        {"status": "ready" if all_up else "degraded", "checks": checks},
        trace_id=get_trace_id(request),
    )
    status_code = 200 if all_up else 503
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))
