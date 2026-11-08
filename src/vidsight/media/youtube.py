"""Bounded YouTube ingestion. All downloads belong to caller's temporary directory."""
import io
import math
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import cv2
from PIL import Image
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from ..providers.base import ConfigurationError, ImageBlock, ProviderResponseError


def video_id(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password or parsed.port:
            raise ValueError
        if parsed.hostname == "youtu.be":
            candidate = parsed.path.strip("/")
        elif parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            candidate = (parse_qs(parsed.query).get("v", [""])[0] if parsed.path == "/watch"
                         else parsed.path.split("/")[-1] if parsed.path.startswith(("/shorts/", "/embed/", "/live/")) else "")
        else:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            raise ValueError
        return candidate
    except ValueError:
        raise ConfigurationError("Provide a valid single-video YouTube URL") from None


class QuietLogger:
    def debug(self, message):
        pass
    def warning(self, message):
        pass
    def error(self, message):
        pass


def download(url: str, directory: Path, max_duration: float = 3600) -> tuple[Path, float]:
    identifier = video_id(url)
    options = {"quiet": True, "no_warnings": True, "logger": QuietLogger(), "noplaylist": True,
               "socket_timeout": 30, "retries": 2, "fragment_retries": 2,
               "format": "best[height<=480]/best", "outtmpl": str(directory / "source.%(ext)s"),
               "max_filesize": 500_000_000}
    try:
        with YoutubeDL(options) as downloader:
            source = f"https://www.youtube.com/watch?v={identifier}"
            info = downloader.extract_info(source, download=False)
            duration = float(info.get("duration") or 0)
            if info.get("is_live") or not math.isfinite(duration) or not 0 < duration <= max_duration:
                raise ConfigurationError("Video must be finite and at most 3600 seconds")
            info = downloader.extract_info(source, download=True)
            path = Path(downloader.prepare_filename(info))
            if not path.is_file():
                raise ProviderResponseError("YouTube download did not produce a media file")
            return path, duration
    except DownloadError:
        raise ProviderResponseError("YouTube download failed; check availability and yt-dlp installation") from None


def extract_frames(path: Path, start: float, end: float, count: int = 12) -> tuple[ImageBlock, ...]:
    capture = cv2.VideoCapture(str(path))
    result = []
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        total = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not capture.isOpened() or not math.isfinite(fps) or fps <= 0 or total <= 0:
            raise ProviderResponseError("Cannot decode video frames")
        first, last = int(start * fps), min(int(end * fps), int(total) - 1)
        if first > last or count < 1:
            raise ConfigurationError("Invalid frame sampling range")
        indices = sorted({round(first + i * (last - first) / max(1, count - 1)) for i in range(count)})
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise ProviderResponseError("A requested frame could not be decoded")
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image.thumbnail((1024, 1024))
            out = io.BytesIO()
            image.save(out, "JPEG")
            result.append(ImageBlock(out.getvalue(), "image/jpeg", index / fps))
    finally:
        capture.release()
    return tuple(result)


def extract_audio(path: Path, destination: Path, start: float, end: float) -> Path:
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(start), "-i", str(path),
                        "-t", str(end - start), "-vn", "-ar", "16000", "-ac", "1",
                        "-c:a", "pcm_s16le", str(destination)], check=True, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        raise ProviderResponseError("Audio extraction failed; verify ffmpeg and audio track") from None
    return destination
