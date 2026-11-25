"""Speech to text with a timestamp for every word, using faster-whisper (runs locally)."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# large-v3-turbo handles Romanian well and is about 8x faster than large-v3.
# The first run downloads it from Hugging Face (about 1.6 GB) into the local cache.
DEFAULT_MODEL = "large-v3-turbo"
DEFAULT_LANGUAGE = "ro"
SAMPLE_RATE = 16_000  # what Whisper models expect: 16 kHz, mono


@dataclass
class Word:
    start: float        # seconds from the start of the clip
    end: float
    text: str
    probability: float  # how sure the model is about this word, 0-1


def load_audio(media_path: Path) -> np.ndarray:
    """The clip's sound as 16 kHz mono floats, decoded by FFmpeg.

    faster-whisper can decode files itself, but its decoder (PyAV) changes
    between versions; FFmpeg is already needed for the proxies, so use it here too.
    """
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(media_path),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-",
    ]
    result = subprocess.run(command, capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype=np.float32)


def load_model(name: str = DEFAULT_MODEL):
    """Load the speech model once; loading takes a few seconds, transcribing reuses it."""
    from faster_whisper import WhisperModel  # imported here so the rest works without it

    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe(model, media_path: Path, language: str = DEFAULT_LANGUAGE) -> list[Word]:
    """Every spoken word in a clip, in order. An empty list means nobody speaks.

    vad_filter skips the silent parts before the model listens (VAD = voice
    activity detection), which avoids invented words in silence and saves time.
    """
    segments, _info = model.transcribe(
        load_audio(media_path),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,  # each take is judged on its own
    )
    words = []
    for segment in segments:
        for word in segment.words or []:
            text = word.word.strip()
            if text:
                words.append(Word(word.start, word.end, text, word.probability))
    return words
