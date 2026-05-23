import pytest

from ekcip_llm.errors import AllLlmProvidersFailedError, LlmProviderError
from ekcip_llm.router import LlmRouter
from ekcip_llm.types import LlmCompletionRequest, LlmMessage, LlmRole


class _FakeProvider:
    def __init__(self, name: str, *, configured: bool = True, fail: bool = False, content: str = "ok") -> None:
        self.name = name
        self._configured = configured
        self._fail = fail
        self._content = content
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    async def complete(self, request: LlmCompletionRequest):
        self.calls += 1
        if self._fail:
            raise LlmProviderError(self.name, "simulated failure", status_code=503)
        from ekcip_llm.types import LlmCompletionResult

        return LlmCompletionResult(content=self._content, provider=self.name, model="test-model")


@pytest.mark.asyncio
async def test_router_uses_first_successful_provider():
    grok = _FakeProvider("grok", fail=True)
    nvidia = _FakeProvider("nvidia", content="from nvidia")
    router = LlmRouter([grok, nvidia])

    result = await router.complete(
        LlmCompletionRequest(messages=[LlmMessage(role=LlmRole.USER, content="hello")])
    )

    assert result.content == "from nvidia"
    assert grok.calls == 1
    assert nvidia.calls == 1


@pytest.mark.asyncio
async def test_router_falls_through_to_gemini():
    grok = _FakeProvider("grok", configured=False)
    nvidia = _FakeProvider("nvidia", fail=True)
    hf = _FakeProvider("huggingface", fail=True)
    gemini = _FakeProvider("gemini", content="from gemini")
    router = LlmRouter([grok, nvidia, hf, gemini])

    result = await router.complete(
        LlmCompletionRequest(messages=[LlmMessage(role=LlmRole.USER, content="hello")])
    )

    assert result.provider == "gemini"
    assert nvidia.calls == 1
    assert hf.calls == 1
    assert gemini.calls == 1


@pytest.mark.asyncio
async def test_router_raises_when_all_fail():
    router = LlmRouter(
        [
            _FakeProvider("grok", fail=True),
            _FakeProvider("nvidia", fail=True),
        ]
    )
    with pytest.raises(AllLlmProvidersFailedError):
        await router.complete(
            LlmCompletionRequest(messages=[LlmMessage(role=LlmRole.USER, content="hello")])
        )
