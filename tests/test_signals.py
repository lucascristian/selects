"""Tests for selects.signals."""

import cv2
import numpy as np
import pytest

from selects.signals import exposure, measure_signals, per_second, read_gray_frames, sharpness


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
    assert set(signals) == {"sharpness", "brightness", "highlights", "shadows"}
    assert all(len(values) == 3 for values in signals.values())
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
