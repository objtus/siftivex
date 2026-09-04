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
}

DEFAULT_EXCLUDE_FLAT_TAGS: frozenset[str] = frozenset({"2D"})

DEFAULT_TAG_NOTES: dict[str, str] = {
    "2D": "flat_tags に付けない。2D作品は 種類/（イラスト・漫画コマ等）で表現。",
    "修正": "画像の加工・編集全般（フィルタ、レタッチ、色調整、トリミング等）。",
}

# VLM プロンプトと応答検証の単一ソース（blueprint §タグの構造 と同期）
NAMESPACE_OPTIONS: dict[str, list[str]] = {
    "種類/": ["写真", "イラスト", "3DCG", "図解/資料", "文章/スクショ", "漫画コマ", "ピクセルアート"],
    "画角/": ["全身", "上半身", "バストアップ", "顔アップ", "パーツクローズアップ"],
    "アングル/": ["正面", "側面", "背面", "俯瞰", "あおり"],
    "人数/": ["0人(物・背景のみ)", "1人", "2人", "3人以上"],
}


def format_namespace_prompt_block(options: dict[str, list[str]] | None = None) -> str:
    opts = options or NAMESPACE_OPTIONS
    lines: list[str] = []
    for namespace, values in opts.items():
        lines.append(f"{namespace}: {', '.join(values)}")
    return "\n".join(lines)


def validate_namespace_tags(namespace_tags: dict[str, Any]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for key, allowed in NAMESPACE_OPTIONS.items():
        value = namespace_tags.get(key)
        if isinstance(value, str) and value in allowed:
            validated[key] = value
    return validated


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


def build_system_prompt(vocabulary: dict[str, Any] | None = None) -> str:
    vocab = vocabulary or load_tag_vocabulary()
    preferred = preferred_tag_names(vocab)
    tag_notes: dict[str, str] = {**DEFAULT_TAG_NOTES, **vocab.get("tag_notes", {})}

    preferred_block = ", ".join(preferred) if preferred else "（未生成 — build_tag_vocabulary.py を実行）"

    notes_lines = "\n".join(f"- {tag}: {note}" for tag, note in tag_notes.items())
    namespace_block = format_namespace_prompt_block()

    return f"""You are an image tagging assistant for a personal art reference archive.
Output ONLY valid JSON. No markdown fences, no explanation, no thinking.

Schema:
{{
  "namespace_tags": {{
    "種類/": "<one value>",
    "画角/": "<one value>",
    "アングル/": "<one value>",
    "人数/": "<one value>"
  }},
  "flat_tags": ["tag1", "tag2"],
  "caption": "one sentence in Japanese"
}}

Rules:
- namespace_tags values MUST be chosen exactly from the allowed lists below
- flat_tags MUST use terms from【優先語彙】when they apply (exact spelling)
-【priority_tags】confirmed visually MUST appear in flat_tags
- Add additional flat_tags freely when they describe the image (no count limit)
- Prefer【優先語彙】but do not omit relevant tags
- flat_tags and caption in Japanese
- Do not contradict the image
- Follow【タグの意味】for ambiguous tags
- Do not duplicate namespace_tags in flat_tags (e.g. 2D → use 種類/ イラスト, not flat 2D)

Allowed namespace values:
{namespace_block}

【タグの意味】
{notes_lines}

【優先語彙】
{preferred_block}
"""


def build_user_prompt(priority_tags: list[str]) -> str:
    priority = ", ".join(priority_tags) if priority_tags else "（なし）"
    return (
        "Analyze this image.\n"
        f"【priority_tags】{priority}\n"
        "Include confirmed priority_tags in flat_tags. "
        "Use【優先語彙】and add any other relevant flat_tags."
    )
