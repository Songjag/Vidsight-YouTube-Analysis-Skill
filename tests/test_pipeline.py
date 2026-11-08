from pathlib import Path

import pytest

from vidsight.core import orchestrator
from vidsight.providers.base import ProviderResponseError, VisionResponse
from vidsight.providers.transcription.base import TranscriptSegment


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setattr(orchestrator, "fetch_subtitles", lambda _: [TranscriptSegment(1, 2, "hello")])
    monkeypatch.setattr(orchestrator.youtube, "download", lambda u, d: (Path(d) / "source.mp4", 10))


def test_raw_timeline(source):
    result = orchestrator.VideoAnalyzer({}).analyze("https://youtu.be/abcdefghijk")
    assert result["source"] == "raw-timeline" and result["analysis"] is None
    assert result["timeline"][0]["text"] == "hello"


def test_no_fallback_after_error(source, monkeypatch):
    class Broken:
        closed = False
        def generate(self, req):
            raise ProviderResponseError("failed")
        def close(self):
            self.closed = True
    provider = Broken()
    monkeypatch.setattr(orchestrator, "create_provider", lambda _: provider)
    analyzer = orchestrator.VideoAnalyzer({"LLM_PROVIDER": "ollama", "LLM_MODEL": "m"})
    with pytest.raises(ProviderResponseError):
        analyzer.analyze("https://youtu.be/abcdefghijk")
    assert provider.closed


def test_text_only_warning(source, monkeypatch):
    class Fake:
        def generate(self, req):
            assert "hello" in req.blocks[0].text
            return VisionResponse("summary", "ollama", "m")
        def close(self):
            pass
    monkeypatch.setattr(orchestrator, "create_provider", lambda _: Fake())
    result = orchestrator.VideoAnalyzer({"LLM_PROVIDER": "ollama", "LLM_MODEL": "m"}).analyze("https://youtu.be/abcdefghijk")
    assert result["source"] == "transcript-only" and result["warnings"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://evil.test/watch?v=abcdefghijk",
                                 "https://youtube.com.evil.test/watch?v=abcdefghijk"])
def test_invalid_video_url(url):
    from vidsight.providers.base import ConfigurationError
    with pytest.raises(ConfigurationError):
        orchestrator.youtube.video_id(url)
