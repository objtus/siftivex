"""Folder rules loader tests."""

from __future__ import annotations

from pathlib import Path

from siftivex.folder_rules import load_folder_rules


def test_load_folder_rules_matches_longest_prefix(tmp_path: Path):
    yaml_text = """
profiles:
  pixiv_bookmarks:
    route_tag: route/pixiv
    metadata: pixiv_hybrid
  under_iphone:
    route_tag: route/under-iphone
    parser: under_iphone_legacy_v1

rules:
  - path_prefix: /archive/pixiv
    profile: pixiv_bookmarks
  - path_prefix: /archive/under.iphone
    profile: under_iphone
"""
    path = tmp_path / "folder_rules.yaml"
    path.write_text(yaml_text.strip(), encoding="utf-8")
    rules = load_folder_rules(path)

    pixiv_file = Path("/archive/pixiv/sub/4826_p0.jpg")
    profile = rules.match(pixiv_file)
    assert profile is not None
    assert profile.route_tag == "route/pixiv"
    assert profile.metadata == "pixiv_hybrid"

    iphone_file = Path("/archive/under.iphone/foo.jpg")
    profile = rules.match(iphone_file)
    assert profile is not None
    assert profile.route_tag == "route/under-iphone"

    unknown = rules.match(Path("/other/x.jpg"))
    assert unknown is None
