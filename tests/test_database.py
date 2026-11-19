"""Tests for selects.database."""

from datetime import datetime

from selects.database import connect, save_clips


def make_record(path: str, duration_s: float, is_log: bool) -> dict:
    return {
        "path": path,
        "file_name": path.split("/")[-1],
        "size_bytes": 1000,
        "duration_s": duration_s,
        "fps": 25.0,
        "width": 3840,
        "height": 2160,
        "rotation": 0,
        "orientation": "horizontal",
        "codec": "h264",
        "pix_fmt": "yuv422p10le",
        "recorded_at_utc": datetime(2026, 7, 29, 14, 18, 34),
        "gamma": "s-log3-cine" if is_log else None,
        "is_log": is_log,
    }


def test_save_clips_and_query_with_sql():
    con = connect(":memory:")  # a temporary database that lives only in memory
    save_clips(con, [
        make_record("/footage/A.MP4", 26.4, True),
        make_record("/footage/B.MP4", 10.0, True),
        make_record("/footage/C.mov", 30.0, False),
    ])

    long_log_clips = con.execute(
        "SELECT file_name FROM clips WHERE is_log AND duration_s > 20"
    ).fetchall()

    assert long_log_clips == [("A.MP4",)]


def test_scanning_the_same_clip_twice_replaces_it():
    con = connect(":memory:")
    save_clips(con, [make_record("/footage/A.MP4", 26.4, True)])
    save_clips(con, [make_record("/footage/A.MP4", 30.0, True)])

    rows = con.execute("SELECT duration_s FROM clips").fetchall()

    assert rows == [(30.0,)]
