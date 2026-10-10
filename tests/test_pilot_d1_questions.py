"""d1 question builder tests."""

from siftivex.pilot.d1_questions import build_d1_question_set, namespace_choice_questions
from siftivex.tag_vocabulary import NAMESPACE_OPTIONS


def test_namespace_choice_covers_all_namespaces():
    q = namespace_choice_questions()
    assert set(q.keys()) == {f"ns_{k.rstrip('/')}" for k in NAMESPACE_OPTIONS}
    for key, spec in q.items():
        assert spec["type"] == "choice"
        assert len(spec["criteria"]) == len(NAMESPACE_OPTIONS[key[3:] + "/"])


def test_build_d1_question_set_merges_config():
    cfg = {
        "decision_questions": [
            {"id": "is_photo", "type": "yes_no", "prompt": "写真？"},
        ]
    }
    q = build_d1_question_set(cfg)
    assert "is_photo" in q
    assert q["is_photo"]["type"] == "noul"
    assert "ns_種類" in q or "ns_画角" in q
