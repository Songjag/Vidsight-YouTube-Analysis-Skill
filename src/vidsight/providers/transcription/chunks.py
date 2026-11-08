"""WAV chunking with bounded calls, offsets and overlap de-duplication."""
import wave
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from ..base import ConfigurationError
from .base import TranscriptSegment, TranscriptionProvider


def transcribe_chunks(provider: TranscriptionProvider, path: Path,
                      max_bytes: int, language: str | None = None) -> tuple[list[TranscriptSegment], int]:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        bytes_per_frame = source.getnchannels() * source.getsampwidth()
        capacity = min(300 * rate, (max_bytes - 128) // bytes_per_frame)
        overlap = rate  # One second overlap to avoid cutting a boundary word.
        if capacity <= overlap:
            raise ConfigurationError("STT_MAX_BYTES too small for a one-second overlap")
        total = source.getnframes()
        if total == 0:
            raise ConfigurationError("Audio has no samples")
        step = capacity - overlap
        count = max(1, (max(0, total - capacity) + step - 1) // step + 1)
        if count > 24:
            raise ConfigurationError("STT would exceed 24 uploads; narrow video range")
        result = []
        with TemporaryDirectory(prefix="vidsight-stt-") as directory:
            for index in range(count):
                offset = index * step
                source.setpos(offset)
                chunk = Path(directory) / "chunk.wav"
                with wave.open(str(chunk), "wb") as out:
                    out.setparams(source.getparams())
                    out.writeframes(source.readframes(min(capacity, total - offset)))
                duration = min(capacity, total - offset) / rate
                for segment in provider.transcribe(chunk, language):
                    if segment.end > duration + 1:
                        raise ConfigurationError("STT segment lies outside audio chunk")
                    adjusted = replace(segment, start=segment.start + offset / rate,
                                       end=min(segment.end, duration) + offset / rate)
                    duplicate = next((old for old in reversed(result[-20:])
                                      if old.text.casefold().strip() == adjusted.text.casefold().strip()
                                      and adjusted.start <= old.end and adjusted.end >= old.start), None)
                    if duplicate is None:
                        result.append(adjusted)
            return sorted(result, key=lambda s: (s.start, s.end)), count
