"""Tests for selects.probe."""

import pytest

from selects.probe import get_duration, get_fps, get_video_stream


def test_get_duration_converts_text_to_float():
    info = {"format": {"duration": "26.400000"}}
    assert get_duration(info) == 26.4


def test_get_video_stream_finds_video_when_it_is_not_first():
    info = {
        "streams": [
            {"index": 0, "codec_type": "audio"},
            {"index": 1, "codec_type": "video"},
        ]
    }
    assert get_video_stream(info)["index"] == 1


def test_get_video_stream_raises_error_when_there_is_no_video():
    info = {"streams": [{"index": 0, "codec_type": "audio"}]}
    with pytest.raises(ValueError):
        get_video_stream(info)


def test_get_fps_with_whole_number_rate():
    stream = {"r_frame_rate": "25/1"}
    assert get_fps(stream) == 25.0


def test_get_fps_with_fractional_rate():
    stream = {"r_frame_rate": "30000/1001"}
    assert get_fps(stream) == pytest.approx(29.97, abs=0.01)