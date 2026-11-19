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


def connect(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    """Open (or create) the database and make sure the tables exist."""
    con = duckdb.connect(str(db_path))
    con.execute(CREATE_CLIPS_TABLE)
    con.execute(CREATE_PROXIES_TABLE)
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
