from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ekcip_api.middleware.trace import get_trace_id
from ekcip_shared.envelope import ApiEnvelope


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        envelope = ApiEnvelope.fail(str(exc.detail), trace_id=get_trace_id(request))
        return JSONResponse(status_code=exc.status_code, content=envelope.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        envelope = ApiEnvelope.fail("Validation error", trace_id=get_trace_id(request))
        return JSONResponse(status_code=422, content=envelope.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        envelope = ApiEnvelope.fail("Internal server error", trace_id=get_trace_id(request))
        return JSONResponse(status_code=500, content=envelope.model_dump(mode="json"))
