"""PID lock helpers for long-running batch jobs."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from siftivex.paths import DATA_DIR

LOCK_DIR = DATA_DIR / "locks"


class LockError(RuntimeError):
    pass


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(name: str) -> Path:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCK_DIR / f"{name}.lock"
    if path.exists():
        try:
            old_pid = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            old_pid = -1
        if old_pid > 0 and _is_alive(old_pid):
            raise LockError(f"Lock held by pid {old_pid}: {path}")
        path.unlink(missing_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")
    return path


def release_lock(path: Path) -> None:
    if path.exists():
        try:
            if int(path.read_text(encoding="utf-8").strip()) == os.getpid():
                path.unlink(missing_ok=True)
        except ValueError:
            path.unlink(missing_ok=True)


@contextmanager
def job_lock(name: str):
    path = acquire_lock(name)
    try:
        yield path
    finally:
        release_lock(path)
