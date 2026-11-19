"""Tests for selects.catalog."""

from datetime import datetime

from selects.catalog import find_videos, make_clip_record, parse_creation_time

# A trimmed copy of what ffprobe returns for an FX30 clip
FX30_INFO = {
    "format": {
        "duration": "26.400000",
        "size": "537152323",
        "tags": {"creation_time": "2026-07-29T14:18:34.000000Z"},
    },
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "pix_fmt": "yuv422p10le",
            "width": 3840,
            "height": 2160,
            "r_frame_rate": "25/1",
        },
        {"index": 1, "codec_type": "audio", "codec_name": "pcm_s16be"},
    ],
}


def test_find_videos_keeps_only_videos_and_skips_hidden_files(tmp_path):
    (tmp_path / "C0001.MP4").touch()
    (tmp_path / "trip").mkdir()
    (tmp_path / "trip" / "phone.mov").touch()
    (tmp_path / "C0001M01.XML").touch()
    (tmp_path / "notes.txt").touch()
    (tmp_path / "._C0001.MP4").touch()

    videos = find_videos(tmp_path)

    assert [video.name for video in videos] == ["C0001.MP4", "phone.mov"]


def test_parse_creation_time_returns_utc():
    assert parse_creation_time(FX30_INFO) == datetime(2026, 7, 29, 14, 18, 34)


def test_parse_creation_time_returns_none_without_tags():
    assert parse_creation_time({"format": {}}) is None


def test_make_clip_record_combines_ffprobe_and_gamma(tmp_path):
    record = make_clip_record(tmp_path / "C0001.MP4", FX30_INFO, "s-log3-cine")

    assert record["file_name"] == "C0001.MP4"
    assert record["duration_s"] == 26.4
    assert record["fps"] == 25.0
    assert (record["width"], record["height"]) == (3840, 2160)
    assert record["size_bytes"] == 537152323
    assert record["is_log"] is True


def test_make_clip_record_swaps_size_for_vertical_clips(tmp_path):
    vertical_info = {
        "format": FX30_INFO["format"],
        "streams": [dict(FX30_INFO["streams"][0], side_data_list=[{"rotation": -90}])],
    }
    record = make_clip_record(tmp_path / "C0002.MP4", vertical_info, None)

    assert (record["width"], record["height"]) == (2160, 3840)
    assert record["rotation"] == -90
    assert record["orientation"] == "vertical"


def test_make_clip_record_without_xml_is_not_log(tmp_path):
    record = make_clip_record(tmp_path / "phone.mov", FX30_INFO, None)
    assert record["gamma"] is None
    assert record["is_log"] is False
