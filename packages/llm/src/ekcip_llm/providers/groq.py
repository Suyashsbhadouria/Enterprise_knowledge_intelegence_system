from ekcip_llm.providers.openai_compatible import OpenAiCompatibleProvider


class GroqProvider(OpenAiCompatibleProvider):
    def __init__(self, api_key: str | None, model: str) -> None:
        super().__init__(
            name="groq",
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            model=model,
        )
