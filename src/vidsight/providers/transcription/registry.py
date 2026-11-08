import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

import httpx

from ..base import AuthenticationError, ConfigurationError, ProviderResponseError
from ..config import boolean, integer, number, validate_url
from .base import TranscriptSegment, normalize


@dataclass(frozen=True)
class STTConfig:
    provider: str
    model: str = ""
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    max_bytes: int = 25_000_000
    timeout: float = 180


def resolve_stt(env: Mapping[str, str]) -> STTConfig:
    name = env.get("STT_PROVIDER") or "auto"
    if name not in {"auto", "none", "youtube_subtitles", "groq_whisper", "openai_whisper", "openai_compatible", "faster_whisper"}:
        raise ConfigurationError("Unknown STT_PROVIDER")
    if name in {"none", "youtube_subtitles"}:
        return STTConfig(name)
    if name == "auto":
        if env.get("GROQ_API_KEY") and boolean(env, "LLM_ALLOW_CLOUD", True):
            name = "groq_whisper"
        elif env.get("STT_MODEL_PATH"):
            name = "faster_whisper"
        else:
            return STTConfig("youtube_subtitles")
    if name == "faster_whisper":
        path = env.get("STT_MODEL_PATH") or ""
        if not Path(path).is_dir() or not path:
            raise ConfigurationError("faster_whisper: STT_MODEL_PATH must be an existing model directory")
        return STTConfig(name, path)
    prefix = "GROQ" if name == "groq_whisper" else "OPENAI"
    default_url = {"groq_whisper": "https://api.groq.com/openai/v1",
                   "openai_whisper": "https://api.openai.com/v1"}.get(name, "")
    url = validate_url(env.get("STT_BASE_URL") or default_url, boolean(env, "LLM_ALLOW_CLOUD", True))
    key = env.get("STT_API_KEY") or (env.get(f"{prefix}_API_KEY") if name != "openai_compatible" else "") or ""
    if name != "openai_compatible" and not key:
        raise ConfigurationError(f"{name}: missing STT_API_KEY or {prefix}_API_KEY")
    model = env.get("STT_MODEL") or {"groq_whisper": "whisper-large-v3", "openai_whisper": "whisper-1"}.get(name, "")
    if not model:
        raise ConfigurationError("Set STT_MODEL for custom transcription endpoint")
    if name == "openai_compatible" and not env.get("STT_MAX_BYTES"):
        raise ConfigurationError("Set verified STT_MAX_BYTES for custom transcription endpoint")
    limit = integer(env, "STT_MAX_BYTES", 25_000_000, 1)
    if name != "openai_compatible" and limit > 25_000_000:
        raise ConfigurationError("STT_MAX_BYTES exceeds supported upload limit")
    return STTConfig(name, model, url, key, limit, number(env, "STT_TIMEOUT_SEC", 180, 0.01))


class HTTPTranscriber:
    def __init__(self, config: STTConfig, *, transport: httpx.BaseTransport | None = None):
        self.config, self.transport = config, transport

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> list[TranscriptSegment]:
        if audio_path.suffix.lower() != ".wav":
            raise ConfigurationError("STT upload expects normalized WAV audio")
        if not 0 < audio_path.stat().st_size <= self.config.max_bytes:
            raise ConfigurationError("STT audio exceeds endpoint size limit; narrow time range")
        data = {"model": self.config.model, "response_format": "verbose_json"}
        if language_hint:
            data["language"] = language_hint
        headers = {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
        logging.getLogger(__name__).info("AI destination host=%s; data=audio", urlsplit(self.config.base_url).hostname)
        try:
            with httpx.Client(transport=self.transport, timeout=self.config.timeout,
                              follow_redirects=False, trust_env=False) as client, audio_path.open("rb") as audio:
                response = client.post(self.config.base_url + "/audio/transcriptions", data=data,
                                       headers=headers, files={"file": ("audio.wav", audio, "audio/wav")})
        except httpx.HTTPError:
            raise ProviderResponseError("STT: network/timeout error; upload not retried") from None
        if response.status_code in {401, 403}:
            raise AuthenticationError(f"STT: HTTP {response.status_code}; check credentials")
        if response.status_code != 200:
            raise ProviderResponseError(f"STT: HTTP {response.status_code}; upload not retried")
        try:
            result = response.json()
            return normalize(result["segments"], result.get("language", language_hint))
        except (ValueError, KeyError, TypeError):
            raise ProviderResponseError("STT: response requires timestamped segments") from None


class FasterWhisperTranscriber:
    def __init__(self, config: STTConfig):
        self.config = config

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> list[TranscriptSegment]:
        try:
            backend = importlib.import_module("faster_whisper")
        except ImportError:
            raise ConfigurationError("Install local STT with uv sync --extra stt-local") from None
        try:
            model = backend.WhisperModel(self.config.model, device="cpu", compute_type="int8", local_files_only=True)
            segments, info = model.transcribe(str(audio_path), language=language_hint)
            rows = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
            return normalize(rows, info.language)
        except Exception:
            raise ProviderResponseError("faster_whisper: model load/transcription failed") from None


def create_transcriber(config: STTConfig):
    if config.provider in {"none", "youtube_subtitles"}:
        return None
    return FasterWhisperTranscriber(config) if config.provider == "faster_whisper" else HTTPTranscriber(config)
