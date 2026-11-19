"""Build the clip catalog: one record of technical metadata per video file."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from selects.probe import get_duration, get_fps, get_rotation, get_video_stream, probe_file
from selects.sony_xml import find_sidecar_xml, is_log, read_gamma

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mxf"}


def find_videos(folder: Path) -> list[Path]:
    """Return every video file in a folder and its subfolders, sorted by path."""
    videos = []
    for path in folder.rglob("*"):
        # Skip hidden files, e.g. the "._C0001.MP4" copies macOS leaves on SD cards
        if path.name.startswith("."):
            continue
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append(path)
    return sorted(videos)


def parse_creation_time(info: dict) -> datetime | None:
    """Return when the clip was recorded, in UTC, or None if the file does not say.

    The result has no time zone attached; by convention it is always UTC.
    """
    text = info["format"].get("tags", {}).get("creation_time")
    if text is None:
        return None
    recorded = datetime.fromisoformat(text)  # e.g. "2026-07-29T14:18:34.000000Z"
    return recorded.astimezone(timezone.utc).replace(tzinfo=None)


def make_clip_record(video_path: Path, info: dict, gamma: str | None) -> dict:
    """Combine ffprobe metadata and the Sony gamma into one flat record."""
    video = get_video_stream(info)
    rotation = get_rotation(video)
    width, height = int(video["width"]), int(video["height"])
    if rotation in (90, -90, 270, -270):
        width, height = height, width  # the frame as the viewer sees it
    return {
        "path": str(video_path.resolve()),
        "file_name": video_path.name,
        "size_bytes": int(info["format"]["size"]),
        "duration_s": get_duration(info),
        "fps": get_fps(video),
        "width": width,
        "height": height,
        "rotation": rotation,
        "orientation": "vertical" if height > width else "horizontal",
        "codec": video["codec_name"],
        "pix_fmt": video.get("pix_fmt"),
        "recorded_at_utc": parse_creation_time(info),
        "gamma": gamma,
        "is_log": is_log(gamma),
    }


def build_clip_record(video_path: Path) -> dict:
    """Read one clip from disk (ffprobe and the Sony XML, if any) and return its record."""
    info = probe_file(video_path)
    gamma = None
    xml_path = find_sidecar_xml(video_path)
    if xml_path is not None:
        try:
            gamma = read_gamma(xml_path)
        except ValueError:
            gamma = None  # the XML exists but has no gamma information
    return make_clip_record(video_path, info, gamma)


def scan_folder(folder: Path) -> tuple[list[dict], list[str]]:
    """Build a record for every clip in a folder.

    Returns the records and a list of problems. One broken file does not stop the scan.
    """
    records = []
    problems = []
    for video_path in find_videos(folder):
        try:
            records.append(build_clip_record(video_path))
        except (subprocess.CalledProcessError, ValueError, KeyError) as error:
            problems.append(f"{video_path.name}: {error}")
    return records, problems
