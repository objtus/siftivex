"""Compare d1 answers to gold namespace labels."""

from __future__ import annotations

from siftivex.tag_vocabulary import NAMESPACE_OPTIONS, parse_namespace_tag


def ns_key_from_question(qname: str) -> str | None:
    if qname.startswith("ns_"):
        return qname[3:] + "/"
    return None


def expected_from_gold(item: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in item.get("namespace_auto") or []:
        parsed = parse_namespace_tag(tag)
        if parsed:
            out[parsed[0]] = parsed[1]
    return out


def predicted_from_d1(d1_block: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not d1_block:
        return out
    answers = d1_block.get("answers")
    if answers is None and "choice" not in str(d1_block):
        return out
    if answers is None:
        answers = {}
    for qname, ans in answers.items():
        ns = ns_key_from_question(qname)
        if not ns or ns not in NAMESPACE_OPTIONS:
            continue
        choice = ans.get("choice") if isinstance(ans, dict) else None
        if choice:
            choice_str = str(choice)
            allowed = NAMESPACE_OPTIONS[ns]
            if choice_str in allowed:
                out[ns] = choice_str
            else:
                for val in allowed:
                    if choice_str == val.replace("/", "_"):
                        out[ns] = val
                        break
                else:
                    out[ns] = choice_str
    return out
