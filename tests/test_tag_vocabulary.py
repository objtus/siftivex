from siftivex.tag_vocabulary import (
    NAMESPACE_OPTIONS,
    build_system_prompt,
    build_user_prompt,
    dedupe_namespace_flat_tags,
    is_noise_tag,
    normalize_tags,
    process_vlm_tags,
    validate_namespace_tags,
)


def test_noise_single_letter():
    assert is_noise_tag("O")
    assert is_noise_tag("Q")
    assert not is_noise_tag("2D")


def test_noise_filter():
    assert is_noise_tag("QbwAE47um")
    assert is_noise_tag("0265")
    assert not is_noise_tag("制服")


def test_normalize_aliases():
    tags = normalize_tags(
        ["眼鏡", "風景", "スクリーンショット"],
        aliases={"眼鏡": "メガネ", "スクリーンショット": "スクショ"},
    )
    assert tags == ["メガネ", "風景", "スクショ"]


def test_normalize_dedupe():
    tags = normalize_tags(["風景", "風景", "QbwAE47um"])
    assert tags == ["風景"]


def test_validate_namespace_tags():
    assert validate_namespace_tags({"種類/": "イラスト", "画角/": "invalid"}) == {"種類/": "イラスト"}
    assert validate_namespace_tags({"光の方向/": "逆光", "髪色/": "黒"}) == {"光の方向/": "逆光"}
    assert validate_namespace_tags("not a dict") == {}


def test_build_system_prompt_includes_light_direction():
    prompt = build_system_prompt({"preferred_flat_tags": [], "manual_flat_tags": [], "tag_notes": {}})
    assert "光の方向/" in prompt
    assert "逆光" in prompt
    assert '"光の方向/": "<one value>"' in prompt


def test_process_vlm_tags_promotes_bare_namespace_values():
    ns, flat = process_vlm_tags(
        {"画角/": "全身"},
        ["逆光", "種類/写真", "街撮り"],
        vocabulary={"aliases": {}, "noise_patterns": ["^$"], "exclude_flat_tags": []},
    )
    assert ns == {"画角/": "全身", "光の方向/": "逆光", "種類/": "写真"}
    assert flat == ["街撮り"]


def test_allowed_namespace_prefixes():
    from siftivex.tag_vocabulary import allowed_namespace_prefixes

    assert "光の方向" in allowed_namespace_prefixes()
    assert "種類" in allowed_namespace_prefixes()
    assert "靴の" not in allowed_namespace_prefixes()


def test_build_system_prompt_includes_all_namespaces():
    prompt = build_system_prompt({"preferred_flat_tags": [], "manual_flat_tags": [], "tag_notes": {}})
    for namespace, values in NAMESPACE_OPTIONS.items():
        assert namespace in prompt
        assert values[0] in prompt


def test_build_system_prompt_max_flat_tags():
    prompt = build_system_prompt({}, max_flat_tags=60)
    assert "up to 60 total" in prompt
    assert "Do NOT treat priority_tags as a checklist" in prompt
    assert "visually confirmed" in prompt
    user = build_user_prompt(["制服", "透け"], max_flat_tags=60)
    assert "filename hints only" in user
    assert "Do NOT pick tags from priority_tags" in user
    assert "max 60" in user


def test_process_vlm_tags_truncates_and_dedupes():
    ns, flat = process_vlm_tags(
        {"種類/": "写真"},
        ["写真", "制服", "透け"] + [f"追加{i}" for i in range(70)],
        vocabulary={"aliases": {}, "noise_patterns": ["^$"], "exclude_flat_tags": []},
        max_flat_tags=60,
        priority_tags=["制服"],
    )
    assert ns == {"種類/": "写真"}
    assert "写真" not in flat
    assert "制服" not in flat
    assert "透け" in flat
    assert len(flat) == 60


def test_process_vlm_tags_drops_invalid_slash_and_promotes_floating():
    ns, flat = process_vlm_tags(
        {},
        ["靴のNR/BRソール", "文章/スクショ", "種類/写真", "街撮り"],
        vocabulary={"aliases": {}, "noise_patterns": [], "exclude_flat_tags": []},
    )
    assert ns == {"種類/": "文章/スクショ"}
    assert flat == ["街撮り"]


def test_process_vlm_tags_applies_aliases():
    ns, flat = process_vlm_tags(
        {},
        ["セーラー襟", "眼鏡"],
        vocabulary={
            "aliases": {"セーラー襟": "セーラー服", "眼鏡": "メガネ"},
            "noise_patterns": [],
            "exclude_flat_tags": [],
        },
    )
    assert ns == {}
    assert flat == ["セーラー服", "メガネ"]


def test_dedupe_namespace_flat_tags():
    tags = ["アングル/正面", "種類/写真", "写真", "制服", "透け"]
    assert dedupe_namespace_flat_tags(tags) == [
        "アングル/正面",
        "種類/写真",
        "制服",
        "透け",
    ]
