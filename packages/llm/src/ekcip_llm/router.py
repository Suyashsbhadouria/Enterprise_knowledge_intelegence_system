from ekcip_llm.errors import AllLlmProvidersFailedError, LlmProviderError
from ekcip_llm.providers.base import LlmProvider
from ekcip_llm.providers.openai_compatible import with_system_prompt
from ekcip_llm.types import LlmCompletionRequest, LlmCompletionResult
from ekcip_shared.logging import get_logger

logger = get_logger(__name__)


class LlmRouter:
    """Try providers in order: Groq → NVIDIA → Hugging Face → Gemini."""

    def __init__(self, providers: list[LlmProvider]) -> None:
        self._providers = providers

    def configured_providers(self) -> list[str]:
        return [provider.name for provider in self._providers if provider.is_configured()]

    async def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        prepared = with_system_prompt(request)
        failures: list[str] = []

        for provider in self._providers:
            if not provider.is_configured():
                failures.append(f"{provider.name}: not configured")
                continue
            try:
                result = await provider.complete(prepared)
                logger.info(
                    "llm_completion_ok",
                    provider=result.provider,
                    model=result.model,
                    task=request.task,
                )
                return result
            except LlmProviderError as exc:
                failures.append(str(exc))
                logger.warning(
                    "llm_provider_failed",
                    provider=provider.name,
                    error=str(exc),
                    status_code=exc.status_code,
                )

        raise AllLlmProvidersFailedError(failures)
