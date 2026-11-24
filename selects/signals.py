"""Per-second visual signals measured on the analysis proxies."""

from collections.abc import Iterator
from pathlib import Path
from statistics import median

import cv2
import numpy as np


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian: high when edges are crisp, low when the frame is blurry.

    The Laplacian highlights places where brightness changes suddenly (edges).
    A sharp frame has many strong edges, so the result varies a lot; a blurry
    frame has soft edges, so the result stays close to zero.
    """
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


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


def measure_sharpness(proxy_path: Path) -> list[float]:
    """Sharpness of every second of a proxy (index 0 = from 0 s to 1 s)."""
    samples = [(time_s, sharpness(gray)) for time_s, gray in read_gray_frames(proxy_path)]
    return per_second(samples)
