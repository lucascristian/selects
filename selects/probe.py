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