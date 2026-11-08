import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from test_http import image_block
from vidsight.providers.base import Capabilities, VisionRequest
from vidsight.providers.config import ProviderConfig
from vidsight.providers.registry import create_provider


@pytest.mark.parametrize("name,path,response", [
    ("anthropic", "/messages", {"content": [{"type": "text", "text": "answer"}], "stop_reason": "end_turn"}),
    ("gemini", "/models/m:generateContent", {"candidates": [{"content": {"parts": [{"text": "answer"}]}, "finishReason": "STOP"}]}),
    ("ollama", "/api/chat", {"message": {"content": "answer"}, "done": True, "done_reason": "stop"}),
])
def test_protocol(name, path, response):
    def handler(req):
        assert req.method == "POST" and req.url.path == path
        body = json.loads(req.content)
        if name == "anthropic":
            assert req.headers["x-api-key"] == "private"
            assert req.headers["anthropic-version"] == "2023-06-01"
            assert body["system"] == "system"
            assert body["messages"][0]["content"][2]["source"]["media_type"] == "image/jpeg"
        elif name == "gemini":
            assert req.headers["x-goog-api-key"] == "private"
            assert "private" not in str(req.url)
            assert body["systemInstruction"]["parts"][0]["text"] == "system"
            assert body["contents"][0]["parts"][2]["inlineData"]["mimeType"] == "image/jpeg"
        else:
            assert body["stream"] is False
            assert body["messages"][0]["role"] == "system"
            assert not body["messages"][1]["images"][0].startswith("data:")
        return httpx.Response(200, json=response)
    provider = create_provider(ProviderConfig(name, "m", "https://example.test", "private",
                               capabilities=Capabilities(supports_images=True)),
                               transport=httpx.MockTransport(handler))
    try:
        result = provider.generate(VisionRequest("system", "question", (image_block(),)))
        assert result.text == "answer" and not result.truncated
    finally:
        provider.close()


def test_gguf_lazy_and_cleanup(monkeypatch):
    calls = []
    class FakeModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def create_chat_completion(self, **kwargs):
            return {"choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}]}
        def close(self):
            calls.append("closed")
    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeModel))
    provider = create_provider(ProviderConfig("gguf", "m", model_path="model.gguf"))
    assert not calls
    assert provider.generate(VisionRequest(None, "question")).text == "answer"
    provider.close()
    assert len(calls) == 2 and calls[-1] == "closed"


def test_gguf_missing_dependency(monkeypatch):
    from vidsight.providers.base import ConfigurationError
    monkeypatch.setitem(sys.modules, "llama_cpp", None)
    provider = create_provider(ProviderConfig("gguf", "m"))
    with pytest.raises(ConfigurationError, match="uv sync --extra local"):
        provider.generate(VisionRequest(None, "question"))
