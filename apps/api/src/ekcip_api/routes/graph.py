from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ekcip_api.middleware.trace import get_trace_id
from ekcip_graph.client import verify_neo4j_connection
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


@router.get("/status")
async def graph_status(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    status = await verify_neo4j_connection(settings)
    envelope = ApiEnvelope.ok(
        {
            "configured": settings.neo4j_configured,
            "aura": settings.neo4j_is_aura,
            "database": settings.neo4j_database,
            "connection": status,
        },
        trace_id=get_trace_id(request),
    )
    code = 200 if status.get("status") in {"up", "skipped"} else 503
    return JSONResponse(status_code=code, content=envelope.model_dump(mode="json"))
