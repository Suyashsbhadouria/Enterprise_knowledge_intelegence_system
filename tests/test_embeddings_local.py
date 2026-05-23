from unittest.mock import AsyncMock, patch

import pytest

from ekcip_knowledge.embeddings import EmbeddingRouter, build_embedding_router
from ekcip_shared.config import Settings


@pytest.mark.asyncio
async def test_local_provider_used_first():
    router = EmbeddingRouter(
        provider_order=["local"],
        local_enabled=True,
        local_model="sentence-transformers/all-MiniLM-L6-v2",
        local_device="cpu",
        gemini_api_key=None,
        gemini_model="text-embedding-004",
        huggingface_api_key=None,
        huggingface_model="sentence-transformers/all-MiniLM-L6-v2",
        nvidia_api_key=None,
        nvidia_model="nvidia/nv-embedqa-e5-v5",
    )
    with patch(
        "ekcip_knowledge.embeddings.embed_local",
        new=AsyncMock(return_value=[0.1, 0.2, 0.3]),
    ):
        vector, provider = await router.embed("hello world")
    assert provider == "local"
    assert len(vector) == 3


def test_build_embedding_router_includes_local_by_default():
    settings = Settings(
        embedding_provider_order="local,nvidia",
        local_embeddings_enabled=True,
    )
    router = build_embedding_router(settings)
    assert "local" in router.configured_providers()
