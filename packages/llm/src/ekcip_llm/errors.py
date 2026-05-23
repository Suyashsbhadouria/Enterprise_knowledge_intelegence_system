class LlmError(Exception):
    """Base LLM error."""


class LlmProviderError(LlmError):
    def __init__(self, provider: str, message: str, *, status_code: int | None = None) -> None:
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


class AllLlmProvidersFailedError(LlmError):
    def __init__(self, failures: list[str]) -> None:
        self.failures = failures
        super().__init__(f"All LLM providers failed: {'; '.join(failures)}")
