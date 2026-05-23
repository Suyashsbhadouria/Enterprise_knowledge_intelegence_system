from ekcip_llm.providers import GeminiProvider, GrokProvider, HuggingFaceProvider, NvidiaProvider
from ekcip_llm.providers.base import LlmProvider
from ekcip_llm.router import LlmRouter
from ekcip_shared.config import Settings


def _parse_provider_order(raw: str) -> list[str]:
    allowed = {"grok", "nvidia", "huggingface", "gemini"}
    order = [part.strip().lower() for part in raw.split(",") if part.strip()]
    return [name for name in order if name in allowed]


def _build_provider_map(settings: Settings) -> dict[str, LlmProvider]:
    return {
        "grok": GrokProvider(settings.xai_api_key, settings.grok_model),
        "nvidia": NvidiaProvider(settings.nvidia_api_key, settings.nvidia_model),
        "huggingface": HuggingFaceProvider(settings.huggingface_api_key, settings.huggingface_model),
        "gemini": GeminiProvider(settings.gemini_api_key, settings.gemini_model),
    }


def build_llm_router(settings: Settings) -> LlmRouter:
    provider_map = _build_provider_map(settings)
    order = _parse_provider_order(settings.llm_provider_order)
    providers = [provider_map[name] for name in order if name in provider_map]
    return LlmRouter(providers)
