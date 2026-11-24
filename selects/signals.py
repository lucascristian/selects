"""Per-second visual signals measured on the analysis proxies."""

import math
from collections.abc import Callable, Iterator
from pathlib import Path
from statistics import fmean, median

import cv2
import numpy as np

HIGHLIGHT_LEVEL = 250
SHADOW_LEVEL = 8

MOTION_WIDTH = 320     # frames are shrunk to this width before tracking (much faster)
MIN_POINTS = 15        # fewer tracked points than this = motion unknown (e.g. a black frame)
SMOOTH_SECONDS = 0.5   # length of the window that gives the smooth, intended camera path


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


def per_second(
    samples: list[tuple[float, float]],
    reduce: Callable[[list[float]], float] = median,
) -> list[float]:
    """Group (time, value) samples by whole second and reduce each second to one number.

    The default median ignores a single odd frame (a flash, a compression glitch)
    better than the average does. Unknown values (NaN) are skipped; a second with
    no known value at all becomes NaN.
    """
    buckets: dict[int, list[float]] = {}
    for time_s, value in samples:
        buckets.setdefault(int(time_s), [])
        if not math.isnan(value):
            buckets[int(time_s)].append(value)
    return [reduce(buckets[s]) if buckets[s] else math.nan for s in sorted(buckets)]


def frame_motion(previous: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    """How far the whole picture moved between two frames (dx, dy).

    Measured in % of the frame's short side, so vertical and horizontal clips
    compare fairly. Returns (NaN, NaN) when there is nothing to track.

    How: find corners in the previous frame, follow each corner into the
    current frame (optical flow), then fit one shift that explains most of the
    corners (RANSAC ignores the few that belong to a moving person or car).
    """
    scale = MOTION_WIDTH / previous.shape[1]
    before = cv2.resize(previous, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    after = cv2.resize(current, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    corners = cv2.goodFeaturesToTrack(before, maxCorners=200, qualityLevel=0.01, minDistance=8)
    if corners is None or len(corners) < MIN_POINTS:
        return math.nan, math.nan
    moved, found, _ = cv2.calcOpticalFlowPyrLK(before, after, corners, None)
    found = found.ravel() == 1
    if found.sum() < MIN_POINTS:
        return math.nan, math.nan

    matrix, _ = cv2.estimateAffinePartial2D(corners[found], moved[found], method=cv2.RANSAC)
    if matrix is None:
        return math.nan, math.nan
    short_side = min(before.shape)
    return 100 * matrix[0, 2] / short_side, 100 * matrix[1, 2] / short_side


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """Average of each value with its neighbours; the edges repeat the first/last value."""
    padded = np.pad(values, window // 2, mode="edge")
    return np.convolve(padded, np.ones(window) / window, mode="valid")


def split_motion(dx: np.ndarray, dy: np.ndarray, fps: float) -> tuple[np.ndarray, np.ndarray]:
    """Split per-frame motion into the intended move and the shake on top of it.

    A smooth pan moves the picture by about the same amount every frame, so its
    moving average is close to the raw motion. Shake changes direction from one
    frame to the next, so it is what is left after removing the moving average.

    Returns (speed, jitter) per frame:
    speed  = smooth movement, in % of the frame per second
    jitter = how far each frame strays from the smooth path, in % of the frame
    """
    unknown = np.isnan(dx) | np.isnan(dy)
    dx, dy = np.where(unknown, 0.0, dx), np.where(unknown, 0.0, dy)

    window = max(3, round(SMOOTH_SECONDS * fps) // 2 * 2 + 1)  # odd, so it is centred
    smooth_dx, smooth_dy = moving_average(dx, window), moving_average(dy, window)

    speed = np.hypot(smooth_dx, smooth_dy) * fps
    jitter = np.hypot(dx - smooth_dx, dy - smooth_dy)
    speed[unknown], jitter[unknown] = math.nan, math.nan
    return speed, jitter


def measure_signals(proxy_path: Path) -> dict[str, list[float]]:
    """Read the proxy once and return every signal per second (index 0 = 0 s to 1 s)."""
    samples: dict[str, list[tuple[float, float]]] = {
        "sharpness": [], "brightness": [], "highlights": [], "shadows": [],
    }
    times, dx, dy = [], [], []
    previous = None
    for time_s, gray in read_gray_frames(proxy_path):
        mean, highlights, shadows = exposure(gray)
        samples["sharpness"].append((time_s, sharpness(gray)))
        samples["brightness"].append((time_s, mean))
        samples["highlights"].append((time_s, highlights))
        samples["shadows"].append((time_s, shadows))

        move = frame_motion(previous, gray) if previous is not None else (math.nan, math.nan)
        times.append(time_s)
        dx.append(move[0])
        dy.append(move[1])
        previous = gray

    signals = {name: per_second(values) for name, values in samples.items()}

    fps = 1 / (times[1] - times[0]) if len(times) > 1 else 25.0
    speed, jitter = split_motion(np.array(dx), np.array(dy), fps)
    signals["motion"] = per_second(list(zip(times, speed.tolist())))
    # mean, not median: a few violent frames are exactly what makes a second shaky
    signals["shake"] = per_second(list(zip(times, jitter.tolist())), reduce=fmean)
    return signals
