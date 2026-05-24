from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ekcip_api.middleware.trace import get_trace_id
from ekcip_shared.envelope import ApiEnvelope

router = APIRouter()


@router.get("/status")
async def llm_status(request: Request) -> JSONResponse:
    router_instance = request.app.state.llm_router
    settings = request.app.state.settings
    envelope = ApiEnvelope.ok(
        {
            "provider_order": settings.llm_provider_order.split(","),
            "configured": router_instance.configured_providers(),
            "models": {
                "groq": settings.groq_model,
                "nvidia": settings.nvidia_model,
                "huggingface": settings.huggingface_model,
                "gemini": settings.gemini_model,
            },
        },
        trace_id=get_trace_id(request),
    )
    return JSONResponse(content=envelope.model_dump(mode="json"))
