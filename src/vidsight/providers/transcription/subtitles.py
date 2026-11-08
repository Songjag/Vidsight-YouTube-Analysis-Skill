"""Subtitle adapter using the supported instance API and finite HTTP timeouts."""
from youtube_transcript_api import YouTubeTranscriptApi, CouldNotRetrieveTranscript
from requests import RequestException, Session

from ..base import ProviderResponseError
from .base import TranscriptSegment, normalize


class TimeoutSession(Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", (10, 30))
        return super().request(method, url, **kwargs)


def fetch_subtitles(identifier: str, languages: tuple[str, ...] = ("vi", "en")) -> list[TranscriptSegment]:
    try:
        with TimeoutSession() as client:
            fetched = YouTubeTranscriptApi(http_client=client).fetch(identifier, languages=languages)
            return normalize(fetched.to_raw_data(), fetched.language_code)
    except (CouldNotRetrieveTranscript, RequestException):
        raise ProviderResponseError("YouTube subtitles unavailable") from None
