"""Load config/model_stack_pilot.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from siftivex.paths import CONFIG_DIR

DEFAULT_PILOT_CONFIG = CONFIG_DIR / "model_stack_pilot.yaml"
EXAMPLE_PILOT_CONFIG = CONFIG_DIR / "model_stack_pilot.yaml.example"


def load_pilot_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_PILOT_CONFIG
    if not cfg_path.is_file():
        cfg_path = EXAMPLE_PILOT_CONFIG
    if not cfg_path.is_file():
        return {}
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
