"""Per-second visual signals measured on the analysis proxies."""

from collections.abc import Iterator
from pathlib import Path
from statistics import median

import cv2
import numpy as np

HIGHLIGHT_LEVEL = 250
SHADOW_LEVEL = 8


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian: high when edges are crisp, low when the frame is blurry.

    The Laplacian highlights places where brightness changes suddenly (edges).
    A sharp frame has many strong edges, so the result varies a lot; a blurry
    frame has soft edges, so the result stays close to zero.
    """
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def exposure(gray: np.ndarray) -> tuple[float, float, float]:
    """Brightness of a frame: (mean 0-255, % of blown highlights, % of crushed shadows).

    A pixel at 250 or more is pure white (detail lost in the highlights);
    a pixel at 8 or less is pure black (detail lost in the shadows).
    """
    pixels = gray.size
    mean = float(gray.mean())
    highlights = 100 * np.count_nonzero(gray >= HIGHLIGHT_LEVEL) / pixels
    shadows = 100 * np.count_nonzero(gray <= SHADOW_LEVEL) / pixels
    return mean, highlights, shadows


def read_gray_frames(video_path: Path) -> Iterator[tuple[float, np.ndarray]]:
    """Yield (time in seconds, grayscale frame) for every frame of a video."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield index / fps, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            index += 1
    finally:
        capture.release()


def per_second(samples: list[tuple[float, float]]) -> list[float]:
    """Group (time, value) samples by whole second and keep the median of each second.

    The median ignores a single odd frame (a flash, a compression glitch)
    better than the average does.
    """
    buckets: dict[int, list[float]] = {}
    for time_s, value in samples:
        buckets.setdefault(int(time_s), []).append(value)
    return [median(buckets[second]) for second in sorted(buckets)]


def measure_signals(proxy_path: Path) -> dict[str, list[float]]:
    """Read the proxy once and return every signal per second (index 0 = 0 s to 1 s)."""
    samples: dict[str, list[tuple[float, float]]] = {
        "sharpness": [], "brightness": [], "highlights": [], "shadows": [],
    }
    for time_s, gray in read_gray_frames(proxy_path):
        mean, highlights, shadows = exposure(gray)
        samples["sharpness"].append((time_s, sharpness(gray)))
        samples["brightness"].append((time_s, mean))
        samples["highlights"].append((time_s, highlights))
        samples["shadows"].append((time_s, shadows))
    return {name: per_second(values) for name, values in samples.items()}
