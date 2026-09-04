from pathlib import Path
from typing import Any

import yaml

from siftivex.paths import PHASE0_CONFIG


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
