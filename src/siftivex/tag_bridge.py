"""Tag bridge: label ↔ (source, tag) groups for search and UI (see docs/specs/tag-bridge.md)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from siftivex.tags_db import SOURCE_AUTO_D1, SOURCE_AUTO_TAGGER, SOURCE_INFERRED_JA

BRIDGE_VERSION = 1

ALLOWED_SOURCES = frozenset(
    {
        "filename",
        SOURCE_AUTO_TAGGER,
        SOURCE_AUTO_D1,
        SOURCE_INFERRED_JA,
        "manual_added",
    }
)


@dataclass
class TagBridgeMember:
    source: str
    tag: str


@dataclass
class TagBridgeEntry:
    label: str
    members: list[TagBridgeMember] = field(default_factory=list)


@dataclass
class TagBridgeDoc:
    version: int
    updated_at: str
    entries: list[TagBridgeEntry]

    @property
    def by_label(self) -> dict[str, TagBridgeEntry]:
        return {e.label: e for e in self.entries}


def empty_tag_bridge() -> TagBridgeDoc:
    return TagBridgeDoc(
        version=BRIDGE_VERSION,
        updated_at=_utc_now(),
        entries=[],
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_tag_bridge(path: Path) -> TagBridgeDoc:
    if not path.is_file():
        return empty_tag_bridge()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return parse_tag_bridge(raw)


def parse_tag_bridge(raw: dict[str, Any]) -> TagBridgeDoc:
    version = int(raw.get("version", 0))
    if version != BRIDGE_VERSION:
        raise ValueError(f"unsupported tag_bridge version: {version}")
    updated_at = str(raw.get("updated_at") or _utc_now())
    entries: list[TagBridgeEntry] = []
    for item in raw.get("entries") or []:
        if not isinstance(item, dict):
            raise ValueError("entry must be object")
        label = str(item.get("label") or "").strip()
        if not label:
            raise ValueError("entry label required")
        members: list[TagBridgeMember] = []
        for m in item.get("members") or []:
            if not isinstance(m, dict):
                raise ValueError("member must be object")
            source = str(m.get("source") or "").strip()
            tag = str(m.get("tag") or "").strip()
            if source not in ALLOWED_SOURCES:
                raise ValueError(f"invalid member source: {source!r}")
            if not tag:
                raise ValueError("member tag required")
            members.append(TagBridgeMember(source=source, tag=tag))
        if not members:
            raise ValueError(f"entry {label!r} has no members")
        entries.append(TagBridgeEntry(label=label, members=members))
    doc = TagBridgeDoc(version=version, updated_at=updated_at, entries=entries)
    validate_tag_bridge(doc)
    return doc


def validate_tag_bridge(doc: TagBridgeDoc) -> None:
    labels: set[str] = set()
    member_keys: set[tuple[str, str]] = set()
    for entry in doc.entries:
        if entry.label in labels:
            raise ValueError(f"duplicate label: {entry.label!r}")
        labels.add(entry.label)
        for m in entry.members:
            key = (m.source, m.tag)
            if key in member_keys:
                raise ValueError(f"duplicate member: {m.source}:{m.tag!r}")
            member_keys.add(key)


def save_tag_bridge(path: Path, doc: TagBridgeDoc) -> TagBridgeDoc:
    validate_tag_bridge(doc)
    out = TagBridgeDoc(
        version=BRIDGE_VERSION,
        updated_at=_utc_now(),
        entries=doc.entries,
    )
    payload = tag_bridge_to_dict(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tag_bridge.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return out


def tag_bridge_to_dict(doc: TagBridgeDoc) -> dict[str, Any]:
    return {
        "version": doc.version,
        "updated_at": doc.updated_at,
        "entries": [
            {
                "label": e.label,
                "members": [{"source": m.source, "tag": m.tag} for m in e.members],
            }
            for e in doc.entries
        ],
    }


def expand_include_token(token: str, doc: TagBridgeDoc | None) -> list[TagBridgeMember] | None:
    """If token matches a bridge label, return OR members; else None (plain tag)."""
    if not doc or not token:
        return None
    entry = doc.by_label.get(token)
    if not entry:
        return None
    return list(entry.members)


def member_to_label_index(doc: TagBridgeDoc | None) -> dict[tuple[str, str], str]:
    if not doc:
        return {}
    out: dict[tuple[str, str], str] = {}
    for entry in doc.entries:
        for m in entry.members:
            out[(m.source, m.tag)] = entry.label
    return out
