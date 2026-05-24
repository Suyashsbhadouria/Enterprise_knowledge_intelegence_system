import re
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, StateGraph

from ekcip_graph.analysis import detect_blockers, merge_context_sections
from ekcip_graph.intent import ISSUE_KEY_PATTERN, classify_graph_intent
from ekcip_graph.retriever import GraphRetriever, format_graph_context
from ekcip_knowledge.plugin import KnowledgePlugin
from ekcip_knowledge.types import Citation, RetrievalHit
from ekcip_llm.router import LlmRouter
from ekcip_llm.types import LlmCompletionRequest, LlmMessage, LlmRole
from ekcip_orchestration.actions.llm_detector import (
    ActionIntent,
    build_action_system_prompt,
    parse_llm_action_response,
)
from ekcip_orchestration.actions.types import ProposedActionDraft
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)

CONFLUENCE_PAGE_ID_PATTERN = re.compile(r"/pages/(\d+)(?:/|$|\?)")
CONFLUENCE_PAGE_REF_PATTERN = re.compile(r"\bpage[:\s#](\d+)\b", re.IGNORECASE)
GITHUB_REF_PATTERN = re.compile(
    r"\b[\w.-]+/[\w.-]+(?:[#!]\d+|@[a-f0-9]{7,40})\b",
    re.IGNORECASE,
)
SLACK_MESSAGE_REF_PATTERN = re.compile(r"\bC[A-Z0-9]{8,}:\d{10,}\b")

MEETING_REF_PATTERN = re.compile(
    r"\b(?:meeting[:\s#]|transcript[:\s#])([\w.-]+)(?::\d+)?\b",
    re.IGNORECASE,
)

QA_SYSTEM_PROMPT = """You are EKCIP, an enterprise knowledge assistant.
Answer using ONLY the provided organizational context (Jira, Confluence, GitHub, Slack, meetings, Neo4j graph).
Prefer graph relationship data for assignee/ownership questions when present.
If context is insufficient, say what is missing and which source would help.
Be concise and factual. Reference issue keys, PRs, commits, pages, and Slack threads when relevant.
Do not invent assignees, statuses, or document content not present in the context."""


@dataclass
class QaState:
    question: str
    history: list[LlmMessage] = field(default_factory=list)
    issue_keys: list[str] = field(default_factory=list)
    page_ids: list[str] = field(default_factory=list)
    github_ids: list[str] = field(default_factory=list)
    slack_ids: list[str] = field(default_factory=list)
    meeting_ids: list[str] = field(default_factory=list)
    hits: list[RetrievalHit] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    context: str = ""
    answer: str = ""
    llm_provider: str | None = None
    llm_model: str | None = None
    graph_modes: list[str] = field(default_factory=list)
    phase: str = "3-qa"


@dataclass
class QaResult:
    answer: str
    phase: str
    citations: list[Citation]
    llm_provider: str | None
    llm_model: str | None
    issue_keys: list[str]
    page_ids: list[str]
    github_ids: list[str]
    slack_ids: list[str]
    meeting_ids: list[str]
    graph_modes: list[str]
    action_intent: ActionIntent = "question"
    action_drafts: list[ProposedActionDraft] = field(default_factory=list)


class QaGraphRunner:
    """Phase 3 LangGraph: understand → retrieve (vector + graph) → analyze → answer."""

    def __init__(
        self,
        knowledge_plugin: KnowledgePlugin,
        llm_router: LlmRouter,
        graph_retriever: GraphRetriever | None = None,
    ) -> None:
        self._knowledge = knowledge_plugin
        self._llm_router = llm_router
        self._graph_retriever = graph_retriever
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(dict)

        async def understand(state: dict) -> dict:
            question = state["question"]
            keys = list(dict.fromkeys(ISSUE_KEY_PATTERN.findall(question)))
            page_ids = list(
                dict.fromkeys(
                    CONFLUENCE_PAGE_ID_PATTERN.findall(question)
                    + CONFLUENCE_PAGE_REF_PATTERN.findall(question)
                )
            )
            github_ids = list(dict.fromkeys(GITHUB_REF_PATTERN.findall(question)))
            slack_ids = list(dict.fromkeys(SLACK_MESSAGE_REF_PATTERN.findall(question)))
            meeting_ids = list(dict.fromkeys(MEETING_REF_PATTERN.findall(question)))
            return {
                **state,
                "issue_keys": keys,
                "page_ids": page_ids,
                "github_ids": github_ids,
                "slack_ids": slack_ids,
                "meeting_ids": meeting_ids,
            }

        async def retrieve(state: dict) -> dict:
            hits, citations = await self._knowledge.retrieve(
                state["question"],
                issue_keys=state.get("issue_keys") or None,
                page_ids=state.get("page_ids") or None,
                github_ids=state.get("github_ids") or None,
                slack_ids=state.get("slack_ids") or None,
                meeting_ids=state.get("meeting_ids") or None,
            )
            vector_context = KnowledgePlugin.format_context(hits, citations)
            graph_context = ""
            graph_modes: list[str] = []
            graph_snippets: list = []
            if self._graph_retriever is not None:
                intent = classify_graph_intent(
                    state["question"],
                    issue_keys=state.get("issue_keys") or None,
                )
                graph_result = await self._graph_retriever.retrieve(intent)
                graph_context = format_graph_context(graph_result)
                graph_modes = list(graph_result.query_modes)
                graph_snippets = list(graph_result.snippets)
            return {
                **state,
                "hits": hits,
                "citations": citations,
                "vector_context": vector_context,
                "graph_context": graph_context,
                "graph_modes": graph_modes,
                "graph_snippets": graph_snippets,
            }

        async def analyze(state: dict) -> dict:
            from ekcip_graph.types import GraphRetrievalResult

            intent = classify_graph_intent(
                state["question"],
                issue_keys=state.get("issue_keys") or None,
            )
            graph_result = GraphRetrievalResult(
                snippets=tuple(state.get("graph_snippets") or []),
                query_modes=tuple(state.get("graph_modes") or []),
            )
            analysis = None
            if intent.wants_blockers or graph_result.snippets:
                analysis = detect_blockers(
                    graph=graph_result,
                    hits=state.get("hits") or [],
                )
            merged = merge_context_sections(
                vector_context=state.get("vector_context") or "",
                graph_context=state.get("graph_context") or "Graph not queried.",
                analysis=analysis,
            )
            return {**state, "context": merged, "analysis": analysis}

        async def answer(state: dict) -> dict:
            configured = self._llm_router.configured_providers()
            if not configured:
                return {
                    **state,
                    "answer": (
                        "No LLM provider configured. Set GROQ_API_KEY, NVIDIA_API_KEY, "
                        "HUGGINGFACE_API_KEY, or GEMINI_API_KEY."
                    ),
                    "phase": "3-qa-no-llm",
                }

            user_prompt = (
                f"Question:\n{state['question']}\n\n"
                f"Organizational context:\n"
                f"{state.get('context') or 'No context available.'}"
            )
            messages = list(state.get("history") or [])
            messages.append(LlmMessage(role=LlmRole.USER, content=user_prompt))

            system_prompt = QA_SYSTEM_PROMPT
            if state.get("actions_enabled"):
                action_prompt = build_action_system_prompt(
                    actions_enabled=True,
                    slack_channel_names=state.get("slack_channel_names") or {},
                    allowed_slack_channels=state.get("allowed_slack_channels") or [],
                )
                if action_prompt.strip():
                    system_prompt = f"{QA_SYSTEM_PROMPT}\n{action_prompt}"

            result = await self._llm_router.complete(
                LlmCompletionRequest(
                    messages=[
                        LlmMessage(role=LlmRole.SYSTEM, content=system_prompt),
                        *messages,
                    ],
                    task="chat",
                )
            )
            parsed = parse_llm_action_response(
                result.content,
                slack_channel_names=state.get("slack_channel_names") or {},
                allowed_slack_channels=state.get("allowed_slack_channels") or [],
                original_question=str(state.get("original_question") or state["question"]),
                actions_enabled=bool(state.get("actions_enabled")),
            )
            final_answer = parsed.visible_reply
            phase = "4-action-proposed" if parsed.intent == "action" and parsed.drafts else "3-qa"
            if parsed.intent == "both" and parsed.drafts:
                phase = "4-qa-proposed"
            return {
                **state,
                "answer": final_answer,
                "llm_provider": result.provider,
                "llm_model": result.model,
                "phase": phase,
                "action_intent": parsed.intent,
                "action_drafts": list(parsed.drafts),
            }

        graph.add_node("understand", understand)
        graph.add_node("retrieve", retrieve)
        graph.add_node("analyze", analyze)
        graph.add_node("answer", answer)
        graph.set_entry_point("understand")
        graph.add_edge("understand", "retrieve")
        graph.add_edge("retrieve", "analyze")
        graph.add_edge("analyze", "answer")
        graph.add_edge("answer", END)
        return graph.compile()

    async def run(
        self,
        *,
        question: str,
        history: list[LlmMessage] | None = None,
        original_question: str | None = None,
        slack_channel_names: dict[str, str] | None = None,
        allowed_slack_channels: list[str] | None = None,
        actions_enabled: bool = True,
    ) -> QaResult:
        initial: dict[str, Any] = {
            "question": question,
            "original_question": original_question or question,
            "history": history or [],
            "issue_keys": [],
            "page_ids": [],
            "hits": [],
            "citations": [],
            "context": "",
            "answer": "",
            "slack_channel_names": dict(slack_channel_names or {}),
            "allowed_slack_channels": list(allowed_slack_channels or []),
            "actions_enabled": actions_enabled,
            "action_intent": "question",
            "action_drafts": [],
        }
        final = await self._graph.ainvoke(initial)
        return QaResult(
            answer=final.get("answer", ""),
            phase=final.get("phase", "3-qa"),
            citations=final.get("citations") or [],
            llm_provider=final.get("llm_provider"),
            llm_model=final.get("llm_model"),
            issue_keys=final.get("issue_keys") or [],
            page_ids=final.get("page_ids") or [],
            github_ids=final.get("github_ids") or [],
            slack_ids=final.get("slack_ids") or [],
            meeting_ids=final.get("meeting_ids") or [],
            graph_modes=final.get("graph_modes") or [],
            action_intent=final.get("action_intent") or "question",
            action_drafts=final.get("action_drafts") or [],
        )
