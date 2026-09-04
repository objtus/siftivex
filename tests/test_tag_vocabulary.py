from siftivex.tag_vocabulary import (
    NAMESPACE_OPTIONS,
    build_system_prompt,
    is_noise_tag,
    normalize_tags,
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


def test_build_system_prompt_includes_all_namespaces():
    prompt = build_system_prompt({"preferred_flat_tags": [], "manual_flat_tags": [], "tag_notes": {}})
    for namespace, values in NAMESPACE_OPTIONS.items():
        assert namespace in prompt
        assert values[0] in prompt
