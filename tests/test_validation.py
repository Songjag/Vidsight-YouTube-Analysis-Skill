import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from vidsight.cli import doctor
from vidsight.providers.base import (ConfigurationError, ProviderResponseError,
                                    ProviderTimeoutError, VisionRequest)
from vidsight.providers.config import ProviderConfig, resolve_config, load_environment
from vidsight.providers.registry import create_provider
from vidsight.providers.transcription.registry import FasterWhisperTranscriber, STTConfig


@pytest.mark.parametrize("provider", ["openai", "openai_compatible", "anthropic", "gemini", "ollama"])
@pytest.mark.parametrize("body", [{}, [], {"choices": []}, {"error": "private transcript"}])
def test_malformed_response_safe(provider, body):
    instance = create_provider(ProviderConfig(provider, "m", "https://test"),
                               transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))
    try:
        with pytest.raises(ProviderResponseError) as caught:
            instance.generate(VisionRequest(None, "secret prompt"))
        assert "private" not in str(caught.value) and "secret" not in str(caught.value)
    finally:
        instance.close()


@pytest.mark.parametrize("provider,response", [
    ("openai", {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}),
    ("anthropic", {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}),
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]}),
    ("ollama", {"message": {"content": "ok"}, "done": True, "done_reason": "stop"}),
])
def test_text_only_wire(provider, response):
    def handler(req):
        body = json.loads(req.content)
        assert "image" not in json.dumps(body).lower()
        return httpx.Response(200, json=response)
    instance = create_provider(ProviderConfig(provider, "m", "https://test"), transport=httpx.MockTransport(handler))
    try:
        assert instance.generate(VisionRequest(None, "question")).text == "ok"
    finally:
        instance.close()


def test_retry_after_over_budget():
    instance = create_provider(ProviderConfig("openai", "m", "https://test", timeout=1),
        transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "3600"})),
        sleep=lambda _: pytest.fail("Should not sleep past budget"))
    with pytest.raises(ProviderTimeoutError):
        instance.generate(VisionRequest(None, "question"))
    instance.close()


def test_environment_precedence(tmp_path, monkeypatch):
    path = tmp_path / "test.env"
    path.write_text("LLM_MODEL=from_file\nOPENAI_API_KEY=test_only\n")
    monkeypatch.setenv("LLM_MODEL", "from_process")
    assert load_environment(path)["LLM_MODEL"] == "from_process"
    assert path.read_text().startswith("LLM_MODEL=from_file")


def test_doctor_offline_and_no_secret():
    result = doctor({"LLM_PROVIDER": "openai", "LLM_MODEL": "m", "OPENAI_API_KEY": "private-key"})
    assert result["network_checked"] is False and result["model_inference_tested"] is False
    assert "private-key" not in json.dumps(result)


def test_gguf_config_validation(tmp_path):
    model, projector = tmp_path / "model.gguf", tmp_path / "mmproj.gguf"
    model.write_bytes(b"fake")
    env = {"LLM_PROVIDER": "gguf", "GGUF_MODEL_PATH": str(model), "LLM_SUPPORTS_IMAGES": "true"}
    with pytest.raises(ConfigurationError):
        resolve_config(env)
    projector.write_bytes(b"fake")
    cfg = resolve_config({**env, "GGUF_CHAT_HANDLER": "llava-1.5", "GGUF_MMPROJ_PATH": str(projector)})
    assert cfg.model == "model" and cfg.capabilities.supports_images


def test_gguf_vision_fake(monkeypatch):
    from test_http import image_block
    from vidsight.providers.base import Capabilities
    closed = []
    class Handler:
        def __init__(self, **kwargs):
            assert kwargs["clip_model_path"] == "projector"
        def close(self):
            closed.append("handler")
    class Model:
        def __init__(self, **kwargs):
            assert isinstance(kwargs["chat_handler"], Handler)
        def create_chat_completion(self, **kwargs):
            assert kwargs["messages"][0]["content"][2]["image_url"]["url"].startswith("data:image/jpeg")
            return {"choices": [{"message": {"content": "ok"}, "finish_reason": "length"}]}
        def close(self):
            closed.append("model")
    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=Model))
    monkeypatch.setitem(sys.modules, "llama_cpp.llama_chat_format", SimpleNamespace(Llava15ChatHandler=Handler))
    cfg = ProviderConfig("gguf", "m", mmproj_path="projector", chat_handler="llava-1.5")
    instance = create_provider(replace(cfg, capabilities=Capabilities(supports_images=True)))
    assert instance.generate(VisionRequest(None, "q", (image_block(),))).truncated
    instance.close()
    assert closed == ["model", "handler"]


def test_local_stt_fake(monkeypatch):
    class Model:
        def __init__(self, path, **kwargs):
            assert kwargs["local_files_only"] is True
        def transcribe(self, path, language=None):
            return iter([SimpleNamespace(start=0, end=1, text=" hello ")]), SimpleNamespace(language="vi")
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    result = FasterWhisperTranscriber(STTConfig("faster_whisper", "model-dir")).transcribe(Path("audio.wav"))
    assert result[0].text == "hello" and result[0].language == "vi"
