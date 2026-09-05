import sqlite3
from pathlib import Path

from siftivex.paths import DEFAULT_DB_PATH, SCHEMA_DIR


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 120000")
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


def migrate_phase1(db_path: Path | None = None) -> bool:
    """Apply Phase 1 additive migration. Returns True if newly applied."""
    path = db_path or DEFAULT_DB_PATH
    migration_path = SCHEMA_DIR / "phase1_migration.sql"
    if not migration_path.exists():
        raise FileNotFoundError(f"Migration not found: {migration_path}")

    conn = get_connection(path)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='images'"
        ).fetchone()
        if row is None:
            raise RuntimeError("Phase 0 base schema missing — run init_db first")

        has_migrations = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if has_migrations:
            already = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 'phase1'"
            ).fetchone()
            if already:
                return False

        conn.executescript(migration_path.read_text(encoding="utf-8"))
        conn.commit()
        return True
    finally:
        conn.close()


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
