import asyncio
import math

import httpx

from ekcip_knowledge.embeddings_local import embed_local
from ekcip_shared.config import Settings
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

HF_ROUTER_FEATURE_EXTRACTION = (
    "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"
)
NVIDIA_EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"


class EmbeddingError(Exception):
    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        super().__init__(f"{provider}: {message}")


class EmbeddingRouter:
    """Embed text: local sentence-transformers, then cloud fallbacks."""

    def __init__(
        self,
        *,
        provider_order: list[str],
        local_enabled: bool,
        local_model: str,
        local_device: str,
        gemini_api_key: str | None,
        gemini_model: str,
        huggingface_api_key: str | None,
        huggingface_model: str,
        nvidia_api_key: str | None,
        nvidia_model: str,
    ) -> None:
        self._provider_order = provider_order
        self._local_enabled = local_enabled
        self._local_model = local_model
        self._local_device = local_device
        self._gemini_api_key = gemini_api_key
        self._gemini_model = gemini_model
        self._huggingface_api_key = huggingface_api_key
        self._huggingface_model = huggingface_model
        self._nvidia_api_key = nvidia_api_key
        self._nvidia_model = nvidia_model

    def configured_providers(self) -> list[str]:
        configured: list[str] = []
        for name in self._provider_order:
            if name == "local" and self._local_enabled:
                configured.append("local")
            elif name == "nvidia" and self._nvidia_api_key:
                configured.append("nvidia")
            elif name == "huggingface" and self._huggingface_api_key:
                configured.append("huggingface")
            elif name == "gemini" and self._gemini_api_key:
                configured.append("gemini")
        return configured

    async def embed(self, text: str) -> tuple[list[float], str]:
        failures: list[str] = []
        for provider in self._provider_order:
            try:
                if provider == "local" and self._local_enabled:
                    return (
                        await embed_local(
                            text,
                            model_name=self._local_model,
                            device=self._local_device,
                        ),
                        "local",
                    )
                if provider == "nvidia" and self._nvidia_api_key:
                    return await self._embed_nvidia(text), "nvidia"
                if provider == "huggingface" and self._huggingface_api_key:
                    return await self._embed_huggingface(text), "huggingface"
                if provider == "gemini" and self._gemini_api_key:
                    return await self._embed_gemini(text), "gemini"
            except EmbeddingError as exc:
                failures.append(str(exc))
                logger.warning("embedding_provider_failed", provider=provider, error=str(exc))
            except (httpx.ConnectError, httpx.NetworkError, OSError) as exc:
                msg = f"network error: {exc}"
                failures.append(f"{provider}: {msg}")
                logger.warning("embedding_provider_network_failed", provider=provider, error=msg)
            except Exception as exc:
                failures.append(f"{provider}: {exc}")
                logger.warning("embedding_provider_failed", provider=provider, error=str(exc))
        raise EmbeddingError("all", f"All embedding providers failed: {failures}")

    async def _embed_nvidia(self, text: str) -> list[float]:
        payload = {
            "input": [text[:8000]],
            "model": self._nvidia_model,
            "input_type": "query",
        }
        headers = {
            "Authorization": f"Bearer {self._nvidia_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(NVIDIA_EMBEDDINGS_URL, headers=headers, json=payload)
        if response.status_code >= 400:
            raise EmbeddingError("nvidia", f"HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        items = data.get("data", [])
        if not items:
            raise EmbeddingError("nvidia", "Missing embedding data in response")
        embedding = items[0].get("embedding")
        if not embedding:
            raise EmbeddingError("nvidia", "Empty embedding vector")
        return [float(v) for v in embedding]

    async def _embed_gemini(self, text: str) -> list[float]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._gemini_model}:embedContent"
        )
        payload = {
            "model": f"models/{self._gemini_model}",
            "content": {"parts": [{"text": text[:8000]}]},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, params={"key": self._gemini_api_key}, json=payload)
        if response.status_code >= 400:
            raise EmbeddingError("gemini", f"HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        values = data.get("embedding", {}).get("values")
        if not values:
            raise EmbeddingError("gemini", "Missing embedding values in response")
        return [float(v) for v in values]

    async def _embed_huggingface(self, text: str) -> list[float]:
        model_path = self._huggingface_model
        url = HF_ROUTER_FEATURE_EXTRACTION.format(model=model_path)
        headers = {"Authorization": f"Bearer {self._huggingface_api_key}"}
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, headers=headers, json={"inputs": text[:8000]})
        if response.status_code >= 400:
            raise EmbeddingError(
                "huggingface",
                f"HTTP {response.status_code}: {response.text[:300]}",
            )
        data = response.json()
        vector = _flatten_embedding(data)
        if not vector:
            raise EmbeddingError("huggingface", "Empty embedding vector")
        return vector


def _flatten_embedding(data: object) -> list[float]:
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], (int, float)):
            return [float(x) for x in data]
        if isinstance(data[0], list):
            return _flatten_embedding(data[0])
    return []


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_embedding_router(settings: Settings) -> EmbeddingRouter:
    order = [
        part.strip().lower()
        for part in settings.embedding_provider_order.split(",")
        if part.strip()
    ]
    allowed = {"local", "nvidia", "gemini", "huggingface"}
    filtered = [name for name in order if name in allowed]
    if not filtered:
        filtered = ["local", "nvidia", "huggingface", "gemini"]

    local_in_order = "local" in filtered
    return EmbeddingRouter(
        provider_order=filtered,
        local_enabled=settings.local_embeddings_enabled and local_in_order,
        local_model=settings.local_embedding_model,
        local_device=settings.local_embedding_device,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_embedding_model,
        huggingface_api_key=settings.huggingface_api_key,
        huggingface_model=settings.huggingface_embedding_model,
        nvidia_api_key=settings.nvidia_api_key,
        nvidia_model=settings.nvidia_embedding_model,
    )
