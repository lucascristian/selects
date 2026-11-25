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

CREATE_WORDS_TABLE = """
CREATE TABLE IF NOT EXISTS words (
    clip_path   VARCHAR NOT NULL,
    position    INTEGER NOT NULL,
    start_s     DOUBLE NOT NULL,
    end_s       DOUBLE NOT NULL,
    word        VARCHAR NOT NULL,
    probability DOUBLE NOT NULL,
    PRIMARY KEY (clip_path, position)
)
"""

CREATE_TRANSCRIBED_TABLE = """
CREATE TABLE IF NOT EXISTS transcribed (
    clip_path   VARCHAR PRIMARY KEY,
    model       VARCHAR NOT NULL,
    seconds     DOUBLE NOT NULL
)
"""

CREATE_TAKES_TABLE = """
CREATE TABLE IF NOT EXISTS takes (
    clip_path   VARCHAR NOT NULL,
    start_s     DOUBLE NOT NULL,
    end_s       DOUBLE NOT NULL,
    line        INTEGER NOT NULL,
    text        VARCHAR NOT NULL,
    score       DOUBLE NOT NULL,
    best        BOOLEAN NOT NULL,
    reasons     VARCHAR[] NOT NULL,
    PRIMARY KEY (clip_path, start_s)
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
    con.execute(CREATE_WORDS_TABLE)
    con.execute(CREATE_TRANSCRIBED_TABLE)
    con.execute(CREATE_TAKES_TABLE)
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


def load_signals(con: duckdb.DuckDBPyConnection, clip_path: str) -> dict[str, list[float]]:
    """Per-second signals of one clip as saved by analyze (NULL comes back as NaN)."""
    rows = con.execute(
        f"SELECT {', '.join(SIGNAL_NAMES)} FROM signals WHERE clip_path = ? ORDER BY second",
        [clip_path],
    ).fetchall()
    return {name: [float("nan") if row[i] is None else row[i] for row in rows]
            for i, name in enumerate(SIGNAL_NAMES)}


def save_words(con: duckdb.DuckDBPyConnection, clip_path: str, words: list,
               model: str, seconds: float) -> None:
    """Replace the transcript of one clip. An empty list records that nobody speaks."""
    con.execute("DELETE FROM words WHERE clip_path = ?", [clip_path])
    if words:
        con.executemany(
            "INSERT INTO words VALUES (?, ?, ?, ?, ?, ?)",
            [[clip_path, i, w.start, w.end, w.text, w.probability] for i, w in enumerate(words)],
        )
    con.execute("INSERT OR REPLACE INTO transcribed VALUES (?, ?, ?)", [clip_path, model, seconds])


def load_words(con: duckdb.DuckDBPyConnection) -> dict[str, list]:
    """The transcript of every transcribed clip, as {clip path: [Word, ...]}."""
    from selects.transcribe import Word

    words: dict[str, list] = {
        path: [] for (path,) in con.execute("SELECT clip_path FROM transcribed").fetchall()
    }
    rows = con.execute(
        "SELECT clip_path, start_s, end_s, word, probability FROM words ORDER BY clip_path, position"
    ).fetchall()
    for clip_path, start, end, text, probability in rows:
        words[clip_path].append(Word(start, end, text, probability))
    return words


def save_takes(con: duckdb.DuckDBPyConnection, takes: list, best_ids: set[int]) -> None:
    """Replace all takes (they are grouped across clips, so they are saved together)."""
    con.execute("DELETE FROM takes")
    if takes:
        con.executemany(
            "INSERT INTO takes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [[t.clip, t.start, t.end, t.group, t.text, t.score, id(t) in best_ids, t.reasons]
             for t in takes],
        )
