"""Production helpers: d1 answers → auto_d1 namespace tags."""

from __future__ import annotations

from typing import Any

from siftivex.pilot.d1_eval import ns_key_from_question, predicted_from_d1
from siftivex.tag_vocabulary import NAMESPACE_OPTIONS


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


def tagger_hint_state(conn, image_id: str, *, limit: int = 10) -> str | None:
    rows = conn.execute(
        """
        SELECT tag FROM image_tags
        WHERE image_id = ? AND source = 'auto_tagger'
        ORDER BY tag
        LIMIT ?
        """,
        (image_id, limit),
    ).fetchall()
    if not rows:
        return None
    tags = [r[0] for r in rows]
    return "tagger hints: " + ", ".join(tags)
