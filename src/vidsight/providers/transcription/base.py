import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..base import ProviderResponseError


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    language: str | None = None


class TranscriptionProvider(Protocol):
    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> list[TranscriptSegment]: ...


def normalize(rows: list[dict], language: str | None = None, offset: float = 0) -> list[TranscriptSegment]:
    result = []
    try:
        for row in rows:
            start = float(row["start"]) + offset
            end = float(row["end"]) + offset if "end" in row else start + float(row["duration"])
            text = row["text"]
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end
                    and isinstance(text, str)):
                raise ValueError("invalid segment")
            if text.strip():
                result.append(TranscriptSegment(start, end, text.strip(), language))
    except (KeyError, ValueError, TypeError):
        raise ProviderResponseError("STT: invalid timestamped segments") from None
    return sorted(result, key=lambda segment: (segment.start, segment.end))
