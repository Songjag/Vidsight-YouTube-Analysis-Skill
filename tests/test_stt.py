import json

import httpx
import pytest

from vidsight.providers.base import ConfigurationError, ProviderResponseError
from vidsight.providers.transcription.base import normalize
from vidsight.providers.transcription.registry import HTTPTranscriber, STTConfig, resolve_stt


def test_policy():
    env = {"GROQ_API_KEY": "private", "LLM_ALLOW_CLOUD": "false"}
    assert resolve_stt(env).provider == "youtube_subtitles"
    with pytest.raises(ConfigurationError):
        resolve_stt({**env, "STT_PROVIDER": "groq_whisper"})
    with pytest.raises(ConfigurationError):
        resolve_stt({"STT_PROVIDER": "unknown"})


def test_segments():
    result = normalize([{"start": 3, "end": 4, "text": " b "},
                        {"start": 0, "duration": 1, "text": "a"}], "vi", 10)
    assert [(s.start, s.end, s.text) for s in result] == [(10, 11, "a"), (13, 14, "b")]
    for start in (-1, float("nan")):
        with pytest.raises(ProviderResponseError):
            normalize([{"start": start, "duration": 1, "text": "bad"}])


def test_upload(tmp_path):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"fixture audio")
    def handler(req):
        assert req.url.path == "/v1/audio/transcriptions"
        assert req.headers["authorization"] == "Bearer private"
        assert b"verbose_json" in req.content and b"fixture audio" in req.content
        return httpx.Response(200, content=json.dumps({"segments": [{"start": 0, "end": 1, "text": "hello"}]}))
    cfg = STTConfig("groq_whisper", "m", "https://test/v1", "private")
    result = HTTPTranscriber(cfg, transport=httpx.MockTransport(handler)).transcribe(path)
    assert result[0].text == "hello"


def test_upload_size_guard(tmp_path):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"too large")
    with pytest.raises(ConfigurationError):
        HTTPTranscriber(STTConfig("openai_compatible", max_bytes=1)).transcribe(path)
