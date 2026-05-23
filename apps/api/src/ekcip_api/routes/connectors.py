from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ekcip_api.middleware.trace import get_trace_id
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


@router.get("/mcp")
async def list_mcp_connectors(request: Request) -> JSONResponse:
    registry = request.app.state.mcp_registry
    envelope = ApiEnvelope.ok(
        {"connectors": registry.list_for_api()},
        trace_id=get_trace_id(request),
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))


@router.get("/runtime/health")
async def runtime_connector_health(request: Request) -> JSONResponse:
    connectors = request.app.state.connectors
    results = []
    for connector in connectors:
        health = await connector.health()
        results.append(health.model_dump())
    envelope = ApiEnvelope.ok({"connectors": results}, trace_id=get_trace_id(request))
    return JSONResponse(content=envelope.model_dump(mode="json"))
