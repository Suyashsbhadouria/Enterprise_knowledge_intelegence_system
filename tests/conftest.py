import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
for path in (
    ROOT / "packages" / "shared" / "src",
    ROOT / "packages" / "connectors" / "src",
    ROOT / "packages" / "llm" / "src",
    ROOT / "packages" / "knowledge" / "src",
    ROOT / "packages" / "orchestration" / "src",
    ROOT / "packages" / "graph" / "src",
    ROOT / "apps" / "api" / "src",
):
    sys.path.insert(0, str(path))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "ekcip_dev_password")

from ekcip_api.app import create_app, lifespan  # noqa: E402
from ekcip_api.db.base import Base  # noqa: E402
from ekcip_api.db import models  # noqa: F401, E402
from ekcip_knowledge.models import KnowledgeBase  # noqa: E402
from ekcip_api.db import session as db_session  # noqa: E402
from ekcip_shared.config import get_settings  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(KnowledgeBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def app(test_engine):
    application = create_app()
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    from ekcip_api.dependencies import get_db

    application.dependency_overrides[get_db] = override_get_session

    original_engine = db_session._engine
    original_factory = db_session._session_factory
    db_session._engine = test_engine
    db_session._session_factory = factory

    async with lifespan(application):
        yield application

    application.dependency_overrides.clear()
    db_session._engine = original_engine
    db_session._session_factory = original_factory


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
