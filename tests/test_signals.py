"""Tests for selects.signals."""

import math

import cv2
import numpy as np
import pytest

from selects.signals import (
    exposure,
    frame_motion,
    measure_signals,
    per_second,
    read_gray_frames,
    sharpness,
    split_motion,
)


def checkerboard(size: int = 120, square: int = 10) -> np.ndarray:
    """A black and white checkerboard: lots of hard edges, like a sharp frame."""
    rows, cols = np.indices((size, size)) // square
    return ((rows + cols) % 2 * 255).astype(np.uint8)


def test_flat_frame_has_zero_sharpness():
    flat = np.full((100, 100), 128, dtype=np.uint8)
    assert sharpness(flat) == 0


def test_blurred_frame_is_less_sharp_than_original():
    sharp = checkerboard()
    blurred = cv2.GaussianBlur(sharp, (15, 15), 5)
    assert sharpness(blurred) < sharpness(sharp) / 10


def test_per_second_groups_by_whole_second_and_takes_median():
    samples = [(0.0, 1.0), (0.4, 100.0), (0.8, 3.0), (1.0, 5.0), (1.9, 7.0)]
    assert per_second(samples) == [3.0, 6.0]


def test_read_gray_frames_gives_times_from_fps(tmp_path):
    video = tmp_path / "tiny.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    for _ in range(25):
        writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.release()

    frames = list(read_gray_frames(video))

    assert len(frames) == 25
    assert frames[0][1].shape == (48, 64)
    assert frames[12][0] == pytest.approx(1.2)
    signals = measure_signals(video)
    assert set(signals) == {"sharpness", "brightness", "highlights", "shadows", "motion", "shake"}
    assert all(len(values) == 3 for values in signals.values())
    assert all(math.isnan(v) for v in signals["shake"])  # nothing to track in black
    assert signals["shadows"] == [100.0, 100.0, 100.0]  # the test video is all black


def test_missing_video_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(read_gray_frames(tmp_path / "missing.mp4"))


def test_exposure_of_mid_grey_has_no_clipping():
    grey = np.full((10, 10), 128, dtype=np.uint8)
    assert exposure(grey) == (128.0, 0.0, 0.0)


def test_exposure_counts_blown_and_crushed_pixels():
    frame = np.full((10, 10), 128, dtype=np.uint8)
    frame[:2] = 255  # 2 of 10 rows pure white -> 20 %
    frame[-1] = 0    # 1 of 10 rows pure black -> 10 %
    mean, highlights, shadows = exposure(frame)
    assert highlights == 20.0
    assert shadows == 10.0
    assert mean == pytest.approx((2 * 255 + 7 * 128 + 0) / 10)


def textured_frame(width: int = 640, height: int = 360) -> np.ndarray:
    """Random blobs: plenty of corners to track, like a real scene."""
    noise = np.random.default_rng(seed=1).integers(0, 255, (height, width)).astype(np.uint8)
    return cv2.GaussianBlur(noise, (9, 9), 2)


def shift(frame: np.ndarray, dx: float, dy: float) -> np.ndarray:
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(frame, matrix, (frame.shape[1], frame.shape[0]),
                          borderMode=cv2.BORDER_REFLECT)


def test_frame_motion_finds_a_known_shift():
    frame = textured_frame()
    dx, dy = frame_motion(frame, shift(frame, 18, 0))
    # 18 px on a 640x360 frame = 5 % of the short side (360 px)
    assert dx == pytest.approx(5.0, abs=0.3)
    assert dy == pytest.approx(0.0, abs=0.3)


def test_frame_motion_is_unknown_on_a_flat_frame():
    flat = np.full((360, 640), 10, dtype=np.uint8)
    dx, dy = frame_motion(flat, flat)
    assert math.isnan(dx) and math.isnan(dy)


def test_steady_pan_is_motion_without_shake():
    dx = np.full(50, 1.0)          # the picture moves 1 % every frame
    speed, jitter = split_motion(dx, np.zeros(50), fps=25)
    assert speed == pytest.approx(np.full(50, 25.0))   # 1 % x 25 frames = 25 % per second
    assert jitter == pytest.approx(np.zeros(50))


def test_back_and_forth_is_shake_without_motion():
    dx = np.tile([1.0, -1.0], 25)  # left, right, left, right...
    speed, jitter = split_motion(dx, np.zeros(50), fps=25)
    assert speed[5:-5].max() < 2.5
    assert jitter[5:-5].min() > 0.9


def test_unknown_frames_stay_unknown():
    dx = np.array([math.nan, 1.0, 1.0, 1.0, 1.0])
    speed, jitter = split_motion(dx, np.zeros(5), fps=6)
    assert math.isnan(speed[0]) and math.isnan(jitter[0])


def test_per_second_skips_unknown_values():
    samples = [(0.0, math.nan), (0.5, 4.0), (1.2, math.nan)]
    result = per_second(samples, reduce=max)
    assert result[0] == 4.0
    assert math.isnan(result[1])
