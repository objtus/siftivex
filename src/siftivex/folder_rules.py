"""Load folder_rules.yaml and match paths to ingest profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from siftivex.paths import FOLDER_RULES_PATH


@dataclass(frozen=True)
class IngestProfile:
    name: str
    route_tag: str
    parser: str | None = None
    metadata: str | None = None
    ocr_engine: str | None = None
    fixed_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FolderRule:
    path_prefix: Path
    profile: IngestProfile


@dataclass(frozen=True)
class FolderRules:
    rules: tuple[FolderRule, ...]

    def match(self, file_path: Path) -> IngestProfile | None:
        resolved = file_path.resolve()
        best: FolderRule | None = None
        best_len = -1
        for rule in self.rules:
            prefix = rule.path_prefix.resolve()
            try:
                resolved.relative_to(prefix)
            except ValueError:
                continue
            if len(str(prefix)) > best_len:
                best = rule
                best_len = len(str(prefix))
        return best.profile if best else None


def _parse_profile(name: str, raw: dict[str, Any]) -> IngestProfile:
    fixed = raw.get("fixed_tags") or []
    return IngestProfile(
        name=name,
        route_tag=str(raw["route_tag"]),
        parser=raw.get("parser"),
        metadata=raw.get("metadata"),
        ocr_engine=raw.get("ocr_engine"),
        fixed_tags=tuple(str(t) for t in fixed),
    )


def load_folder_rules(path: Path | None = None) -> FolderRules:
    config_path = path or FOLDER_RULES_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"Folder rules not found: {config_path}\n"
            f"Copy config/folder_rules.yaml.example to config/folder_rules.yaml"
        )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    profiles = {
        name: _parse_profile(name, body)
        for name, body in (raw.get("profiles") or {}).items()
    }
    rules: list[FolderRule] = []
    for entry in raw.get("rules") or []:
        profile_name = entry["profile"]
        if profile_name not in profiles:
            raise KeyError(f"Unknown profile {profile_name!r} in folder rules")
        rules.append(
            FolderRule(
                path_prefix=Path(entry["path_prefix"]),
                profile=profiles[profile_name],
            )
        )
    rules.sort(key=lambda r: len(str(r.path_prefix)), reverse=True)
    return FolderRules(rules=tuple(rules))
