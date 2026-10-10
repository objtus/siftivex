"""Build LiquidAI d1 question dicts from Siftivex namespace vocabulary."""

from __future__ import annotations

from typing import Any

from siftivex.tag_vocabulary import NAMESPACE_OPTIONS


def namespace_choice_questions() -> dict[str, dict[str, Any]]:
    """One choice question per namespace key (e.g. ns_画角)."""
    questions: dict[str, dict[str, Any]] = {}
    for ns, values in NAMESPACE_OPTIONS.items():
        key = ns.rstrip("/")
        criteria = {v.replace("/", "_"): v for v in values}
        questions[f"ns_{key}"] = {
            "type": "choice",
            "instructions": f"この画像の「{key}」に最も当てはまるものを1つ選んでください。",
            "criteria": criteria,
        }
    return questions


def extra_questions_from_config(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in cfg.get("decision_questions") or []:
        if not isinstance(item, dict):
            continue
        qid = item.get("id")
        if not qid:
            continue
        qtype = item.get("type", "yes_no")
        if qtype in ("yes_no", "noul"):
            out[str(qid)] = {
                "type": "noul",
                "instructions": str(item.get("prompt", item.get("instructions", ""))),
            }
        elif qtype == "choice" and isinstance(item.get("criteria"), dict):
            out[str(qid)] = {
                "type": "choice",
                "instructions": str(item.get("prompt", item.get("instructions", ""))),
                "criteria": item["criteria"],
            }
    return out


def build_d1_question_set(cfg: dict[str, Any] | None = None, *, include_namespace: bool = True) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    if include_namespace:
        questions.update(namespace_choice_questions())
    if cfg:
        questions.update(extra_questions_from_config(cfg))
    return questions
