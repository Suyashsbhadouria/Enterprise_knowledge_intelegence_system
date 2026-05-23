import httpx

from ekcip_llm.errors import LlmProviderError
from ekcip_llm.providers.base import LlmProvider
from ekcip_llm.types import LlmCompletionRequest, LlmCompletionResult, LlmMessage, LlmRole


class OpenAiCompatibleProvider(LlmProvider):
    """OpenAI-style chat/completions for Grok, NVIDIA NIM, and Hugging Face router."""

    def __init__(
        self,
        *,
        name: str,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.name = name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    async def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        if not self.is_configured():
            raise LlmProviderError(self.name, "API key not configured")

        payload = {
            "model": self._model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            detail = response.text[:500]
            raise LlmProviderError(
                self.name,
                f"HTTP {response.status_code}: {detail}",
                status_code=response.status_code,
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmProviderError(self.name, f"Unexpected response shape: {data}") from exc

        if not content or not str(content).strip():
            raise LlmProviderError(self.name, "Empty completion content")

        return LlmCompletionResult(
            content=str(content).strip(),
            provider=self.name,
            model=self._model,
        )


def default_system_message(task: str) -> str:
    base = (
        "You are EKCIP, an enterprise knowledge and coordination assistant. "
        "Answer clearly and concisely. If you lack data, say so."
    )
    if task == "summarize":
        return base + " Focus on decisions, owners, blockers, and open questions."
    if task == "plan":
        return base + " Produce actionable steps with dependencies."
    if task == "extract":
        return base + " Return structured facts only, no speculation."
    return base


def with_system_prompt(request: LlmCompletionRequest) -> LlmCompletionRequest:
    if any(message.role == LlmRole.SYSTEM for message in request.messages):
        return request
    system = LlmMessage(role=LlmRole.SYSTEM, content=default_system_message(request.task))
    return request.model_copy(update={"messages": [system, *request.messages]})
