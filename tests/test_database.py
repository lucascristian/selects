"""Tests for selects.database."""

import math
from datetime import datetime

from selects.best_segment import Pick
from selects.database import connect, save_clips, save_pick, save_signals


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


def test_signals_and_picks_are_saved(tmp_path):
    con = connect(tmp_path / "test.duckdb")
    signals = {name: [1.0, 2.0] for name in
               ["sharpness", "brightness", "highlights", "shadows", "motion", "shake"]}
    signals["shake"] = [math.nan, 0.2]
    save_signals(con, "/clips/A.MP4", signals)
    save_signals(con, "/clips/A.MP4", signals)  # running twice must not duplicate rows
    save_pick(con, "/clips/A.MP4", Pick(1, 2, 0.9, ["1-2 s kept"]))

    rows = con.execute("SELECT second, shake FROM signals ORDER BY second").fetchall()
    assert rows == [(0, None), (1, 0.2)]
    assert con.execute("SELECT start_s, end_s, reasons FROM picks").fetchone() == (1, 2, ["1-2 s kept"])
