"""Store the clip catalog and proxy results in a DuckDB database file."""

from pathlib import Path

import duckdb

CLIP_COLUMNS = [
    "path",
    "file_name",
    "size_bytes",
    "duration_s",
    "fps",
    "width",
    "height",
    "rotation",
    "orientation",
    "codec",
    "pix_fmt",
    "recorded_at_utc",
    "gamma",
    "is_log",
]

CREATE_CLIPS_TABLE = """
CREATE TABLE IF NOT EXISTS clips (
    path            VARCHAR PRIMARY KEY,
    file_name       VARCHAR NOT NULL,
    size_bytes      BIGINT,
    duration_s      DOUBLE,
    fps             DOUBLE,
    width           INTEGER,
    height          INTEGER,
    rotation        INTEGER,
    orientation     VARCHAR,
    codec           VARCHAR,
    pix_fmt         VARCHAR,
    recorded_at_utc TIMESTAMP,
    gamma           VARCHAR,
    is_log          BOOLEAN
)
"""

CREATE_PROXIES_TABLE = """
CREATE TABLE IF NOT EXISTS proxies (
    clip_path   VARCHAR PRIMARY KEY,
    proxy_path  VARCHAR NOT NULL,
    lut_applied BOOLEAN NOT NULL,
    seconds     DOUBLE NOT NULL
)
"""


CREATE_SIGNALS_TABLE = """
CREATE TABLE IF NOT EXISTS signals (
    clip_path   VARCHAR NOT NULL,
    second      INTEGER NOT NULL,
    sharpness   DOUBLE,
    brightness  DOUBLE,
    highlights  DOUBLE,
    shadows     DOUBLE,
    motion      DOUBLE,
    shake       DOUBLE,
    PRIMARY KEY (clip_path, second)
)
"""

CREATE_PICKS_TABLE = """
CREATE TABLE IF NOT EXISTS picks (
    clip_path   VARCHAR PRIMARY KEY,
    start_s     INTEGER,
    end_s       INTEGER,
    score       DOUBLE NOT NULL,
    reasons     VARCHAR[] NOT NULL
)
"""

SIGNAL_NAMES = ["sharpness", "brightness", "highlights", "shadows", "motion", "shake"]


def connect(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    """Open (or create) the database and make sure the tables exist."""
    con = duckdb.connect(str(db_path))
    con.execute(CREATE_CLIPS_TABLE)
    con.execute(CREATE_PROXIES_TABLE)
    con.execute(CREATE_SIGNALS_TABLE)
    con.execute(CREATE_PICKS_TABLE)
    return con


def save_clips(con: duckdb.DuckDBPyConnection, records: list[dict]) -> None:
    """Save clip records. A clip that is already in the catalog (same path) is replaced."""
    column_list = ", ".join(CLIP_COLUMNS)
    placeholders = ", ".join("?" for _ in CLIP_COLUMNS)
    sql = f"INSERT OR REPLACE INTO clips ({column_list}) VALUES ({placeholders})"
    for record in records:
        con.execute(sql, [record[column] for column in CLIP_COLUMNS])


def save_proxy(
    con: duckdb.DuckDBPyConnection,
    clip_path: str,
    proxy_path: str,
    lut_applied: bool,
    seconds: float,
) -> None:
    """Record that a proxy was made for a clip and how long it took."""
    con.execute(
        "INSERT OR REPLACE INTO proxies VALUES (?, ?, ?, ?)",
        [clip_path, proxy_path, lut_applied, seconds],
    )


def save_signals(con: duckdb.DuckDBPyConnection, clip_path: str, signals: dict[str, list[float]]) -> None:
    """Replace the per-second signals of one clip. Unknown values (NaN) are stored as NULL."""
    con.execute("DELETE FROM signals WHERE clip_path = ?", [clip_path])
    seconds = len(signals["sharpness"])
    rows = []
    for second in range(seconds):
        values = [signals[name][second] for name in SIGNAL_NAMES]
        rows.append([clip_path, second] + [None if value != value else value for value in values])
    con.executemany("INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)


def save_pick(con: duckdb.DuckDBPyConnection, clip_path: str, pick) -> None:
    """Record the recommended segment of one clip and the reasons for it."""
    con.execute(
        "INSERT OR REPLACE INTO picks VALUES (?, ?, ?, ?, ?)",
        [clip_path, pick.start_s, pick.end_s, pick.score, pick.reasons],
    )
