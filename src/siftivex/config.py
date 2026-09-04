from pathlib import Path
from typing import Any

import yaml

from siftivex.paths import CONFIG_DIR, PHASE0_CONFIG

PATHS_CONFIG = CONFIG_DIR / "paths.yaml"


def load_phase0_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or PHASE0_CONFIG
    if not config_path.exists():
        example = config_path.with_suffix(".yaml.example")
        if example.name.endswith(".yaml.example"):
            example = config_path.parent / "phase0.yaml.example"
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            f"Copy {example} to {config_path} and set source paths."
        )
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_paths_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or PATHS_CONFIG
    if not config_path.exists():
        example = CONFIG_DIR / "paths.yaml.example"
        raise FileNotFoundError(
            f"Paths config not found: {config_path}\n"
            f"Copy {example} to {config_path} and set archive paths."
        )
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def archive_server_path(archive_key: str, paths_config: dict[str, Any] | None = None) -> Path:
    cfg = paths_config or load_paths_config()
    archives = cfg.get("archives") or {}
    if archive_key not in archives:
        known = ", ".join(sorted(archives)) or "(none)"
        raise KeyError(f"Unknown archive {archive_key!r}. Known: {known}")
    entry = archives[archive_key]
    server = entry.get("server")
    if not server:
        raise ValueError(f"Archive {archive_key!r} has no server path configured")
    return Path(server)
