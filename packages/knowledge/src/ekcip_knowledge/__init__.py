"""Vector knowledge indexing and retrieval (Phase 1)."""

from ekcip_knowledge.embeddings import EmbeddingRouter, build_embedding_router
from ekcip_knowledge.retrieval import KnowledgeRetriever
from ekcip_knowledge.types import Citation, KnowledgeChunkRecord, RetrievalHit

__all__ = [
    "Citation",
    "EmbeddingRouter",
    "KnowledgeChunkRecord",
    "KnowledgeRetriever",
    "RetrievalHit",
    "build_embedding_router",
]
