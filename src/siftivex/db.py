import sqlite3
from pathlib import Path

from siftivex.paths import DEFAULT_DB_PATH, SCHEMA_DIR


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | None = None, schema: str = "phase0.sql") -> Path:
    path = db_path or DEFAULT_DB_PATH
    schema_path = SCHEMA_DIR / schema
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    conn = get_connection(path)
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    return path


def log_pipeline_run(
    conn: sqlite3.Connection,
    task: str,
    status: str,
    details: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_runs (task, status, finished_at, details)
        VALUES (?, ?, datetime('now'), ?)
        """,
        (task, status, details),
    )
    conn.commit()
