from ekcip_graph.retriever import GraphRetriever
from ekcip_knowledge.embeddings import build_embedding_router
from ekcip_knowledge.plugin import KnowledgePlugin
from ekcip_knowledge.retrieval import KnowledgeRetriever
from ekcip_knowledge.store import KnowledgeStore
from ekcip_llm.router import LlmRouter
from ekcip_orchestration.qa_graph import QaGraphRunner
from ekcip_shared.config import Settings
from sqlalchemy.ext.asyncio import AsyncSession


def build_qa_runner(
    session: AsyncSession,
    settings: Settings,
    llm_router: LlmRouter,
) -> QaGraphRunner:
    store = KnowledgeStore(session)
    embedding_router = build_embedding_router(settings)
    retriever = KnowledgeRetriever(store, embedding_router)
    plugin = KnowledgePlugin(retriever)
    graph_retriever = GraphRetriever(settings) if settings.neo4j_configured else None
    return QaGraphRunner(plugin, llm_router, graph_retriever)
