"""d1 → auto_d1 namespace mapping."""

from __future__ import annotations

from siftivex.d1_namespace import namespace_tags_from_d1


def test_namespace_tags_from_d1_respects_min_prob():
    block = {
        "answers": {
            "ns_画角": {
                "choice": "全身",
                "probabilities": {"全身": 0.9, "上半身": 0.1},
            },
            "ns_人数": {
                "choice": "1人",
                "probabilities": {"1人": 0.2, "2人": 0.8},
            },
            "ns_種類": {
                "choice": "写真",
                "probabilities": {"写真": 0.99},
            },
        }
    }
    out = namespace_tags_from_d1(block, min_choice_prob=0.4)
    assert out["種類/"] == "写真"
    assert out["画角/"] == "全身"
    assert "人数/" not in out
