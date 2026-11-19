"""Read technical metadata from video files using ffprobe."""

import json
import subprocess
from pathlib import Path


def probe_file(video_path: Path) -> dict:
    """Run ffprobe on a video file and return its metadata as a dictionary."""
    command = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def get_duration(info: dict) -> float:
    """Return the clip duration in seconds as a number."""
    return float(info["format"]["duration"])


def get_video_stream(info: dict) -> dict:
    """Return the first video stream from ffprobe metadata."""
    for stream in info["streams"]:
        if stream["codec_type"] == "video":
            return stream
    raise ValueError("No video stream found")


def get_fps(stream: dict) -> float:
    """Return the frame rate of a stream as a number, e.g. "25/1" -> 25.0."""
    numerator, denominator = stream["r_frame_rate"].split("/")
    return float(numerator) / float(denominator)