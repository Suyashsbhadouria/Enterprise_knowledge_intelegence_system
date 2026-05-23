from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ekcip_api.db.session import get_session
from ekcip_shared.config import Settings, get_settings

API_KEY_HEADER = "X-API-Key"


async def get_db() -> AsyncSession:
    async for session in get_session():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_app_settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return token or None
    return None


async def verify_api_key(request: Request, settings: SettingsDep) -> str | None:
    """Auth from headers only (not OpenAPI parameters) so /docs stays simple in dev."""
    if settings.app_env == "development" and not settings.api_key:
        return "dev-anonymous"
    if not settings.api_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    token = request.headers.get(API_KEY_HEADER) or _extract_bearer_token(request)
    if not token or token != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or missing API key. Send header {API_KEY_HEADER} or Authorization: Bearer <key>",
        )
    return token


AuthSubject = Annotated[str | None, Depends(verify_api_key)]
