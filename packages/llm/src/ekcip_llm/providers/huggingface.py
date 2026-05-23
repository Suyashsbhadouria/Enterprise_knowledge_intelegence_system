from ekcip_llm.providers.openai_compatible import OpenAiCompatibleProvider


class HuggingFaceProvider(OpenAiCompatibleProvider):
    def __init__(self, api_key: str | None, model: str) -> None:
        super().__init__(
            name="huggingface",
            api_key=api_key,
            base_url="https://router.huggingface.co/v1",
            model=model,
        )
