"""Production helpers: d1 answers → auto_d1 namespace tags."""

from __future__ import annotations

from typing import Any

from siftivex.filename_tags import parse_legacy_filename_tags
from siftivex.pixiv_filename import parse_pixiv_filename, parse_pixiv_filename_fallback
from siftivex.pilot.d1_eval import ns_key_from_question, predicted_from_d1
from siftivex.tag_vocabulary import NAMESPACE_OPTIONS, load_tag_vocabulary, normalize_tags


def _choice_probability(ans: dict[str, Any]) -> float | None:
    probs = ans.get("probabilities")
    if not isinstance(probs, dict):
        return None
    choice = ans.get("choice")
    if choice is None:
        return None
    for key in (choice, str(choice)):
        if key in probs:
            try:
                return float(probs[key])
            except (TypeError, ValueError):
                return None
    return None


def namespace_tags_from_d1(
    d1_block: dict[str, Any] | None,
    *,
    min_choice_prob: float = 0.0,
    always_keep_ns: frozenset[str] | None = frozenset({"種類/"}),
) -> dict[str, str]:
    """Map d1 `system_one` output to namespace key → value (for auto_d1 storage)."""
    predicted = predicted_from_d1(d1_block)
    if not d1_block or min_choice_prob <= 0 and not always_keep_ns:
        return predicted

    answers = d1_block.get("answers")
    if not isinstance(answers, dict):
        return predicted

    out: dict[str, str] = {}
    for qname, ans in answers.items():
        ns = ns_key_from_question(qname)
        if not ns or ns not in NAMESPACE_OPTIONS or ns not in predicted:
            continue
        if always_keep_ns and ns in always_keep_ns:
            out[ns] = predicted[ns]
            continue
        if not isinstance(ans, dict):
            out[ns] = predicted[ns]
            continue
        prob = _choice_probability(ans)
        if prob is None or prob >= min_choice_prob:
            out[ns] = predicted[ns]
    return out


def _filename_tags_from_db(conn, image_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT tag FROM image_tags
        WHERE image_id = ? AND source = 'filename'
        ORDER BY tag
        """,
        (image_id,),
    ).fetchall()
    return [r[0] for r in rows]


def is_under_legacy_filename_for_d1(
    file_name: str,
    *,
    route_tag: str | None = None,
) -> bool:
    """True when filename tags are under 旧形式（pixiv 側 filename タグは False）。"""
    name = file_name or ""
    if route_tag == "route/pixiv":
        return False
    if parse_pixiv_filename(name) or parse_pixiv_filename_fallback(name):
        return False
    return bool(parse_legacy_filename_tags(name))


def ordered_legacy_under_filename_tags(
    conn, image_id: str, file_name: str | None = None
) -> list[str]:
    """
    under.iphone 旧ファイル名（`ID_タグ-タグ.ext`）由来の filename タグのみ。

    pixiv ダウンローダの filename タグ（オリジナル, SF, …）は **含めない**。
    """
    row = conn.execute(
        "SELECT file_name, route_tag FROM images WHERE image_id = ?",
        (image_id,),
    ).fetchone()
    if file_name is None:
        file_name = row["file_name"] if row else ""
    route_tag = row["route_tag"] if row else None

    if not is_under_legacy_filename_for_d1(file_name or "", route_tag=route_tag):
        return []

    raw = parse_legacy_filename_tags(file_name or "")
    if not raw:
        return []

    db_tags = _filename_tags_from_db(conn, image_id)
    if not db_tags:
        return []

    db_set = set(db_tags)
    vocab = load_tag_vocabulary()
    ordered = normalize_tags(
        raw,
        aliases=vocab.get("aliases"),
        noise_patterns=vocab.get("noise_patterns"),
    )
    seen: set[str] = set()
    tags: list[str] = []
    for tag in ordered:
        if tag in db_set and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    for tag in db_tags:
        if tag not in seen:
            tags.append(tag)
    return tags


def filename_hint_state(
    conn,
    image_id: str,
    *,
    limit: int = 0,
    file_name: str | None = None,
) -> str | None:
    """
    Build d1 `state` from under 旧ファイル名タグのみ（pixiv filename は渡さない）。

    limit < 0 → no text hints (None). limit == 0 → all tags. limit > 0 → cap count.
    """
    if limit < 0:
        return None
    tags = ordered_legacy_under_filename_tags(conn, image_id, file_name=file_name)
    if not tags:
        return None
    if limit > 0:
        tags = tags[:limit]
    return "filename tags: " + ", ".join(tags)


def d1_state_text_from_config(
    conn,
    image_id: str,
    d1_cfg: dict,
    *,
    file_name: str | None = None,
) -> str | None:
    """Resolve d1 state string from config (filename hints only; tagger not used)."""
    source = str(d1_cfg.get("state_hint_source", "filename")).strip().lower()
    if source in ("none", "off", "vision_only"):
        return None
    if source != "filename":
        raise ValueError(f"Unsupported d1.state_hint_source: {source!r}")
    limit = int(d1_cfg.get("filename_hint_limit", 0))
    return filename_hint_state(conn, image_id, limit=limit, file_name=file_name)
