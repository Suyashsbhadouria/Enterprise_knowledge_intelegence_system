from dataclasses import dataclass, field


@dataclass(frozen=True)
class GraphSnippet:
    """Structured fact from Neo4j for LLM context."""

    kind: str
    label: str
    detail: str
    source_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GraphRetrievalResult:
    snippets: tuple[GraphSnippet, ...]
    query_modes: tuple[str, ...]
    node_count: int | None = None

    @property
    def has_data(self) -> bool:
        return bool(self.snippets)
