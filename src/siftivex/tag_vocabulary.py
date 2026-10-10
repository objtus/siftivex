"""Tag vocabulary: normalization, noise filter, prompt helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from siftivex.paths import CONFIG_DIR, TAG_VOCABULARY_PATH

DEFAULT_NOISE_PATTERNS = [
    r"^\d+$",
    r"^[0-9A-Fa-f]{6,8}$",
    r"^[0-9A-Za-z]$",  # O, E, Q 等（1文字のみ）
    r"^[0-9A-Za-z]{4,}$",  # QbwAE47um 等
]

DEFAULT_ALIASES: dict[str, str] = {
    "眼鏡": "メガネ",
    "スクリーンショット": "スクショ",
    "セーラー襟": "セーラー服",
}

DEFAULT_EXCLUDE_FLAT_TAGS: frozenset[str] = frozenset({"2D"})

DEFAULT_TAG_NOTES: dict[str, str] = {
    "2D": "flat_tags に付けない。2D作品は 種類/（イラスト・漫画コマ等）で表現。",
    "修正": "画像の加工・編集全般（フィルタ、レタッチ、色調整、トリミング等）。",
    "順光": "flat 不可 → 光の方向/ 順光。光源が被写体の後ろ側にある場合は 逆光。",
    "逆光": "flat 不可 → 光の方向/ 逆光。",
}

# VLM プロンプトと応答検証の単一ソース（blueprint §タグの構造 と同期）
NAMESPACE_OPTIONS: dict[str, list[str]] = {
    "種類/": ["写真", "イラスト", "3DCG", "図解/資料", "文章/スクショ", "漫画コマ", "ピクセルアート"],
    "画角/": ["全身", "上半身", "バストアップ", "顔アップ", "パーツクローズアップ"],
    "アングル/": ["正面", "側面", "背面", "俯瞰", "あおり"],
    "光の方向/": ["順光", "逆光", "側光", "上光", "下光"],
    "人数/": ["0人(物・背景のみ)", "1人", "2人", "3人以上"],
}

DEFAULT_MAX_FLAT_TAGS = 60

# Bump when prompt rules change (surfaced in /retag for verification).
PROMPT_REVISION = "2026-09-07-priority-visual"


def namespace_keys() -> list[str]:
    return list(NAMESPACE_OPTIONS.keys())


def allowed_namespace_prefixes() -> frozenset[str]:
    """Prefix strings before the first slash in stored namespace tags (e.g. 種類, 光の方向)."""
    return frozenset(ns.rstrip("/") for ns in NAMESPACE_OPTIONS)


def build_namespace_schema_json() -> str:
    entries = [f'    "{key}": "<one value>"' for key in NAMESPACE_OPTIONS]
    return "{\n" + ",\n".join(entries) + "\n  }"


def format_namespace_prompt_block(options: dict[str, list[str]] | None = None) -> str:
    opts = options or NAMESPACE_OPTIONS
    lines: list[str] = []
    for namespace, values in opts.items():
        lines.append(f"{namespace}: {', '.join(values)}")
    return "\n".join(lines)


def validate_namespace_tags(namespace_tags: dict[str, Any]) -> dict[str, str]:
    """Keep only known namespace keys with values from the allowed list."""
    validated: dict[str, str] = {}
    if not isinstance(namespace_tags, dict):
        return validated
    for key, allowed in NAMESPACE_OPTIONS.items():
        value = namespace_tags.get(key)
        if isinstance(value, str) and value in allowed:
            validated[key] = value
    return validated


def is_allowed_namespace_stored_tag(tag: str) -> bool:
    return parse_namespace_tag(tag) is not None


def parse_namespace_tag(tag: str) -> tuple[str, str] | None:
    """Return (namespace_key, value) if tag is a valid stored namespace tag."""
    for ns, values in NAMESPACE_OPTIONS.items():
        if not tag.startswith(ns):
            continue
        value = tag[len(ns) :]
        if value in values:
            return ns, value
    return None


def find_namespace_for_value(value: str) -> tuple[str, str] | None:
    """Map a namespace value (e.g. 写真, 文章/スクショ) to its namespace key."""
    for ns, values in NAMESPACE_OPTIONS.items():
        if value in values:
            return ns, value
    return None


def namespace_values_from_tags(tags: list[str]) -> set[str]:
    """Collect namespace values present as full namespace tag strings."""
    values: set[str] = set()
    for tag in tags:
        parsed = parse_namespace_tag(tag)
        if parsed:
            values.add(parsed[1])
    return values


def dedupe_namespace_flat_tags(tags: list[str]) -> list[str]:
    """Drop flat tags whose value is already expressed as a namespace tag (P7)."""
    covered = namespace_values_from_tags(tags)
    if not covered:
        return tags
    return [t for t in tags if parse_namespace_tag(t) is not None or t not in covered]


def process_vlm_tags(
    namespace_tags: dict[str, str],
    flat_tags: list[str],
    *,
    vocabulary: dict[str, Any] | None = None,
    max_flat_tags: int = DEFAULT_MAX_FLAT_TAGS,
    priority_tags: list[str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Post-process VLM output: promote/drop slash tags, normalize, dedupe, truncate."""
    vocab = vocabulary or load_tag_vocabulary()
    ns = dict(namespace_tags)
    priority = set(priority_tags or [])
    exclude = excluded_flat_tags(vocab)

    remaining_flat: list[str] = []
    for raw in flat_tags:
        tag = str(raw).strip()
        if not tag:
            continue

        parsed = parse_namespace_tag(tag)
        if parsed:
            ns_key, ns_val = parsed
            ns.setdefault(ns_key, ns_val)
            continue

        if "/" in tag:
            found = find_namespace_for_value(tag)
            if found:
                ns_key, ns_val = found
                ns.setdefault(ns_key, ns_val)
            continue

        remaining_flat.append(tag)

    flat = normalize_tags(
        remaining_flat,
        aliases=vocab.get("aliases"),
        noise_patterns=vocab.get("noise_patterns"),
    )
    flat = [t for t in flat if t not in exclude]

    promoted_flat: list[str] = []
    for tag in flat:
        found = find_namespace_for_value(tag)
        if found:
            ns_key, ns_val = found
            ns.setdefault(ns_key, ns_val)
        else:
            promoted_flat.append(tag)
    flat = promoted_flat

    ns_values = set(ns.values())
    flat = [t for t in flat if t not in ns_values]

    if priority:
        flat = [t for t in flat if t not in priority]

    return ns, flat[:max_flat_tags]


def load_tag_vocabulary(path: Path | None = None) -> dict[str, Any]:
    vocab_path = path or TAG_VOCABULARY_PATH
    if not vocab_path.exists():
        return {
            "preferred_flat_tags": [],
            "manual_flat_tags": [],
            "aliases": dict(DEFAULT_ALIASES),
            "tag_notes": dict(DEFAULT_TAG_NOTES),
            "noise_patterns": list(DEFAULT_NOISE_PATTERNS),
        }
    with vocab_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("aliases", dict(DEFAULT_ALIASES))
    data.setdefault("tag_notes", dict(DEFAULT_TAG_NOTES))
    data.setdefault("manual_flat_tags", [])
    data.setdefault("exclude_flat_tags", sorted(DEFAULT_EXCLUDE_FLAT_TAGS))
    data.setdefault("noise_patterns", DEFAULT_NOISE_PATTERNS)
    return data


def excluded_flat_tags(vocabulary: dict[str, Any]) -> set[str]:
    raw = vocabulary.get("exclude_flat_tags", DEFAULT_EXCLUDE_FLAT_TAGS)
    return {str(tag) for tag in raw}


def is_noise_tag(tag: str, noise_patterns: list[str] | None = None) -> bool:
    patterns = noise_patterns or DEFAULT_NOISE_PATTERNS
    return any(re.fullmatch(p, tag) for p in patterns)


def normalize_tag(tag: str, aliases: dict[str, str] | None = None) -> str:
    tag = tag.strip()
    if not tag:
        return tag
    aliases = aliases or {}
    return aliases.get(tag, tag)


def normalize_tags(
    tags: list[str],
    *,
    aliases: dict[str, str] | None = None,
    noise_patterns: list[str] | None = None,
) -> list[str]:
    aliases = aliases or {}
    patterns = noise_patterns or DEFAULT_NOISE_PATTERNS
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        tag = normalize_tag(tag, aliases)
        if not tag or is_noise_tag(tag, patterns) or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def preferred_tag_names(vocabulary: dict[str, Any]) -> list[str]:
    exclude = excluded_flat_tags(vocabulary)
    entries = vocabulary.get("preferred_flat_tags", [])
    auto: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            auto.append(entry)
        elif isinstance(entry, dict) and "tag" in entry:
            auto.append(str(entry["tag"]))

    manual = [str(t) for t in vocabulary.get("manual_flat_tags", [])]
    seen: set[str] = set()
    merged: list[str] = []
    for tag in auto + manual:
        if not tag or tag in exclude or tag in seen:
            continue
        seen.add(tag)
        merged.append(tag)
    return merged


def build_system_prompt(
    vocabulary: dict[str, Any] | None = None,
    *,
    max_flat_tags: int = DEFAULT_MAX_FLAT_TAGS,
    enable_thinking: bool = False,
    max_thinking_chars: int | None = None,
) -> str:
    vocab = vocabulary or load_tag_vocabulary()
    preferred = preferred_tag_names(vocab)
    tag_notes: dict[str, str] = {**DEFAULT_TAG_NOTES, **vocab.get("tag_notes", {})}

    preferred_block = ", ".join(preferred) if preferred else "（未生成 — build_tag_vocabulary.py を実行）"

    notes_lines = "\n".join(f"- {tag}: {note}" for tag, note in tag_notes.items())
    namespace_block = format_namespace_prompt_block()
    namespace_schema = build_namespace_schema_json()

    if enable_thinking:
        char_limit = max_thinking_chars or 400
        output_rule = (
            f"You may think briefly first (keep reasoning under {char_limit} characters). "
            "After thinking, output ONLY valid JSON in the final message — no markdown fences."
        )
    else:
        output_rule = "Output ONLY valid JSON. No markdown fences, no explanation, no thinking."

    return f"""You are an image tagging assistant for a personal art reference archive.
{output_rule}

Schema:
{{
  "namespace_tags": {namespace_schema},
  "flat_tags": ["tag1", "tag2"],
  "caption": "one sentence in Japanese"
}}

Rules:
- namespace_tags: use ONLY the keys listed in the schema; pick one value per key from the allowed lists below
- omit a namespace key when uncertain (do not invent keys or values)
- values containing slash (e.g. 図解/資料, 文章/スクショ) belong under 種類/ only — never as floating flat tags
- flat_tags MUST reflect ONLY what is clearly visible in the image — never guess or infer from filename
-【priority_tags】are filename-derived hints only; they may be wrong, outdated, or irrelevant to this image
- Do NOT treat priority_tags as a checklist; never add a tag just because it appears in priority_tags
- Do not re-output priority_tags in flat_tags (they are stored separately even when correct)
- When a visible concept matches a term, use exact spelling from【優先語彙】;【優先語彙】is NOT a list to fill from
- Add flat_tags only for visually confirmed content, up to {max_flat_tags} total; fewer tags is OK
- Prefer accuracy over coverage; an empty or small flat_tags list is better than incorrect tags
- flat_tags must NOT contain slash-separated tags; use namespace_tags for structured values
- Do not output synonymous tags together; use the canonical form from【優先語彙】
- Summarize fine-grained variants into one tag (e.g. prefer まつげ over まつげカール/パーマ/…)
- flat_tags and caption in Japanese; caption MUST be one full descriptive sentence
- Do not contradict the image
- Follow【タグの意味】for ambiguous tags
- Do not duplicate namespace_tags in flat_tags (e.g. 2D → use 種類/ イラスト; 逆光 → use 光の方向/ 逆光, not flat 逆光)

Allowed namespace values:
{namespace_block}

【タグの意味】
{notes_lines}

【優先語彙】
{preferred_block}
"""


def build_user_prompt(priority_tags: list[str], *, max_flat_tags: int = DEFAULT_MAX_FLAT_TAGS) -> str:
    priority = ", ".join(priority_tags) if priority_tags else "（なし）"
    return (
        "Analyze this image.\n"
        f"【priority_tags】{priority}\n"
        "priority_tags are filename hints only — they may not match this image. "
        "Do NOT copy them into flat_tags. Do NOT pick tags from priority_tags unless clearly visible. "
        f"Add flat_tags only for what you see (max {max_flat_tags}; fewer is fine)."
    )
