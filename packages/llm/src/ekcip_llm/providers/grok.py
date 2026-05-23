from ekcip_llm.providers.openai_compatible import OpenAiCompatibleProvider


class GrokProvider(OpenAiCompatibleProvider):
    def __init__(self, api_key: str | None, model: str) -> None:
        super().__init__(
            name="grok",
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            model=model,
        )
