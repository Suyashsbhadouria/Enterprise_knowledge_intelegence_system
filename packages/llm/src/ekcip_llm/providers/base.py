from abc import ABC, abstractmethod

from ekcip_llm.types import LlmCompletionRequest, LlmCompletionResult


class LlmProvider(ABC):
    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        raise NotImplementedError
