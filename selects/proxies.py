"""Create small analysis proxies: 720p, 8-bit H.264, with the log LUT applied."""

import subprocess
import time
from pathlib import Path

# Official Sony LUT for S-Gamut3.Cine / S-Log3, installed together with DaVinci Resolve
DEFAULT_SONY_LUT = Path(
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/Sony/"
    "SLog3SGamut3.CineToLC-709.cube"
)
PROXY_HEIGHT = 720


def proxy_path_for(video_path: Path, proxies_dir: Path) -> Path:
    """Return where the proxy of a clip is saved, e.g. C0001.MP4 -> C0001_proxy.mp4."""
    return proxies_dir / f"{video_path.stem}_proxy.mp4"


def build_proxy_command(video_path: Path, proxy_path: Path, lut_path: Path | None) -> list[str]:
    """Return the ffmpeg command that makes a proxy, applying the LUT if one is given."""
    filters = [f"scale=-2:{PROXY_HEIGHT}"]
    if lut_path is not None:
        filters.append(f"lut3d=file='{lut_path}'")
    filters.append("format=yuv420p")
    return [
        "ffmpeg",
        "-y",
        "-v", "error",
        "-i", str(video_path),
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(proxy_path),
    ]


def make_proxy(video_path: Path, proxy_path: Path, lut_path: Path | None) -> float:
    """Create the proxy and return how many seconds it took."""
    proxy_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_proxy_command(video_path, proxy_path, lut_path)
    start = time.perf_counter()
    subprocess.run(command, capture_output=True, text=True, check=True)
    return time.perf_counter() - start
