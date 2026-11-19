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


def get_rotation(stream: dict) -> int:
    """Return how many degrees the player must rotate the video (0 if not rotated).

    A camera held vertically still records a landscape frame (e.g. 3840x2160)
    and stores a rotation tag such as -90 so players show it upright.
    """
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            return int(side_data["rotation"])
    return 0