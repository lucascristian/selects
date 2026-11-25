"""Tests for selects.transcribe (the speech model itself is not loaded here)."""

import subprocess

import numpy as np
import pytest

from selects.transcribe import SAMPLE_RATE, load_audio, transcribe


def test_load_audio_gives_16_khz_mono(tmp_path):
    clip = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-ac", "2", "-ar", "48000", str(clip)],
        check=True,
    )
    audio = load_audio(clip)
    assert audio.dtype == np.float32
    assert len(audio) == pytest.approx(2 * SAMPLE_RATE, abs=SAMPLE_RATE * 0.05)


class FakeWord:
    def __init__(self, start, end, word, probability):
        self.start, self.end, self.word, self.probability = start, end, word, probability


class FakeSegment:
    def __init__(self, words):
        self.words = words


class FakeModel:
    """Stands in for faster-whisper: returns fixed segments, like the real model does."""

    def transcribe(self, audio, **options):
        assert options["word_timestamps"] and options["language"] == "ro"
        segments = [
            FakeSegment([FakeWord(0.5, 0.9, " Bună", 0.9), FakeWord(0.9, 1.2, " ziua.", 0.8)]),
            FakeSegment([FakeWord(1.3, 1.4, " ", 0.1)]),  # empty words are dropped
        ]
        return iter(segments), None


def test_transcribe_returns_clean_words(tmp_path):
    clip = tmp_path / "silence.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=d=1", str(clip)],
                   check=True)
    result = transcribe(FakeModel(), clip)
    assert [w.text for w in result] == ["Bună", "ziua."]
    assert result[0].start == 0.5
