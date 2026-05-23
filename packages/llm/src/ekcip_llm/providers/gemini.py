import httpx

from ekcip_llm.errors import LlmProviderError
from ekcip_llm.providers.base import LlmProvider
from ekcip_llm.types import LlmCompletionRequest, LlmCompletionResult, LlmRole


class GeminiProvider(LlmProvider):
    """Google Gemini generateContent API (last fallback)."""

    name = "gemini"

    def __init__(self, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    async def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        if not self.is_configured():
            raise LlmProviderError(self.name, "API key not configured")

        system_parts: list[str] = []
        contents: list[dict] = []
        for message in request.messages:
            if message.role == LlmRole.SYSTEM:
                system_parts.append(message.content)
                continue
            role = "user" if message.role == LlmRole.USER else "model"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        if not contents:
            raise LlmProviderError(self.name, "No user/assistant messages provided")

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent"
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                params={"key": self._api_key},
                json=payload,
            )

        if response.status_code >= 400:
            raise LlmProviderError(
                self.name,
                f"HTTP {response.status_code}: {response.text[:500]}",
                status_code=response.status_code,
            )

        data = response.json()
        try:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmProviderError(self.name, f"Unexpected response shape: {data}") from exc

        if not content or not str(content).strip():
            raise LlmProviderError(self.name, "Empty completion content")

        return LlmCompletionResult(
            content=str(content).strip(),
            provider=self.name,
            model=self._model,
        )
