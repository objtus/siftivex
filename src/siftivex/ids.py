from pathlib import Path

import blake3


def content_hash(path: Path) -> str:
    """BLAKE3-256 hex digest of file bytes."""
    hasher = blake3.blake3()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def image_id_from_hash(full_hash: str) -> str:
    """Derive image_id: img_ + first 16 hex chars of content_hash."""
    return f"img_{full_hash[:16]}"
