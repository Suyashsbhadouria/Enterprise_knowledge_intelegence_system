"""On-device embeddings via sentence-transformers (downloads model on first use)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ekcip_shared.logging import get_logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = get_logger(__name__)

_loaded_model_name: str | None = None
_loaded_model: SentenceTransformer | None = None
_load_lock = asyncio.Lock()


def _load_model(model_name: str, device: str) -> SentenceTransformer:
    global _loaded_model, _loaded_model_name
    if _loaded_model is not None and _loaded_model_name == model_name:
        return _loaded_model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Run: pip install sentence-transformers"
        ) from exc

    logger.info("local_embedding_model_loading", model=model_name, device=device)
    model = SentenceTransformer(model_name, device=device)
    _loaded_model = model
    _loaded_model_name = model_name
    logger.info("local_embedding_model_ready", model=model_name, device=device)
    return model


def _encode_sync(text: str, model_name: str, device: str) -> list[float]:
    model = _load_model(model_name, device)
    vector = model.encode(text[:8000], normalize_embeddings=True)
    return [float(v) for v in vector.tolist()]


async def embed_local(text: str, *, model_name: str, device: str = "cpu") -> list[float]:
    async with _load_lock:
        # Ensure single-threaded first load; encode still runs in thread pool.
        return await asyncio.to_thread(_encode_sync, text, model_name, device)
