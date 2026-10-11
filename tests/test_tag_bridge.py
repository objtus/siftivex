"""Tag bridge file validation and expansion."""

from __future__ import annotations

from pathlib import Path

import pytest

from siftivex.tag_bridge import (
    TagBridgeEntry,
    TagBridgeMember,
    empty_tag_bridge,
    expand_include_token,
    load_tag_bridge,
    parse_tag_bridge,
    save_tag_bridge,
)


def test_empty_load(tmp_path: Path):
    doc = load_tag_bridge(tmp_path / "missing.json")
    assert doc.entries == []


def test_roundtrip_save(tmp_path: Path):
    path = tmp_path / "tag_bridge.json"
    doc = empty_tag_bridge()
    doc.entries.append(
        TagBridgeEntry(
            label="制服",
            members=[
                TagBridgeMember(source="filename", tag="制服"),
                TagBridgeMember(source="auto_tagger", tag="serafuku"),
            ],
        )
    )
    save_tag_bridge(path, doc)
    loaded = load_tag_bridge(path)
    assert loaded.entries[0].label == "制服"
    assert len(loaded.entries[0].members) == 2


def test_duplicate_member_rejected():
    raw = {
        "version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "entries": [
            {
                "label": "a",
                "members": [{"source": "auto_tagger", "tag": "x"}],
            },
            {
                "label": "b",
                "members": [{"source": "auto_tagger", "tag": "x"}],
            },
        ],
    }
    with pytest.raises(ValueError, match="duplicate member"):
        parse_tag_bridge(raw)


def test_expand_label():
    doc = parse_tag_bridge(
        {
            "version": 1,
            "updated_at": "2026-01-01T00:00:00Z",
            "entries": [
                {
                    "label": "制服",
                    "members": [
                        {"source": "filename", "tag": "制服"},
                        {"source": "auto_tagger", "tag": "serafuku"},
                    ],
                }
            ],
        }
    )
    members = expand_include_token("制服", doc)
    assert members is not None
    assert len(members) == 2
    assert expand_include_token("unknown", doc) is None
