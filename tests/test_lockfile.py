"""Lockfile tests."""

from __future__ import annotations

import pytest

from siftivex.lockfile import LockError, acquire_lock, job_lock, release_lock


def test_job_lock_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr("siftivex.lockfile.LOCK_DIR", tmp_path)
    with job_lock("test"):
        with pytest.raises(LockError):
            acquire_lock("test")
    assert not (tmp_path / "test.lock").exists()


def test_release_lock_only_owner(tmp_path, monkeypatch):
    monkeypatch.setattr("siftivex.lockfile.LOCK_DIR", tmp_path)
    path = acquire_lock("x")
    path.write_text("99999", encoding="utf-8")
    release_lock(path)
    assert path.exists()
