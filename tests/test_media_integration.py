"""Offline integration: real generated video, OpenCV and ffmpeg; no model."""
import shutil
import subprocess
import wave

import pytest

from vidsight.media.youtube import extract_audio, extract_frames
from vidsight.providers.transcription.base import TranscriptSegment
from vidsight.providers.transcription.chunks import transcribe_chunks


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_real_media(tmp_path):
    video = tmp_path / "fixture.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=160x90:r=10:d=2", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-c:v", "mpeg4", "-c:a", "aac",
                    "-shortest", str(video)], check=True, capture_output=True, timeout=20)
    frames = extract_frames(video, 0, 2, 3)
    assert len(frames) == 3
    assert frames[0].timestamp == 0 and frames[-1].timestamp == pytest.approx(1.9)
    audio = extract_audio(video, tmp_path / "audio.wav", 0.5, 1.5)
    with wave.open(str(audio)) as source:
        assert source.getframerate() == 16000 and source.getnchannels() == 1
        assert source.getnframes() / source.getframerate() == pytest.approx(1, abs=.1)
    assert video.exists()  # Input file belongs to caller.


def test_chunk_offsets_overlap_cleanup(tmp_path):
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as out:
        out.setparams((1, 2, 100, 0, "NONE", "not compressed"))
        out.writeframes(b"\0\0" * 500)
    paths = []
    class Fake:
        def transcribe(self, path, language=None):
            paths.append(path)
            # Two chunks: [0,3], [2,5]. The same event appears in overlap.
            return [TranscriptSegment(2, 3, "boundary")] if len(paths) == 1 else [
                TranscriptSegment(0, 1, "boundary"), TranscriptSegment(1, 2, "later")]
    result, calls = transcribe_chunks(Fake(), audio, 728)
    assert calls == 2
    assert [(s.start, s.end, s.text) for s in result] == [(2, 3, "boundary"), (3, 4, "later")]
    assert all(not p.exists() for p in paths)
    assert audio.exists()
