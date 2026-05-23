from ekcip_llm.providers.openai_compatible import OpenAiCompatibleProvider


class NvidiaProvider(OpenAiCompatibleProvider):
    def __init__(self, api_key: str | None, model: str) -> None:
        super().__init__(
            name="nvidia",
            api_key=api_key,
            base_url="https://integrate.api.nvidia.com/v1",
            model=model,
        )
