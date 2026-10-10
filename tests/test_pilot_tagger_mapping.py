"""cl_tagger tag mapping loader (synthetic JSON)."""

import json

from siftivex.pilot.tagger_cl import load_tag_mapping


def test_load_tag_mapping_idx_to_tag_format(tmp_path):
    mapping = {
        "idx_to_tag": {"0": "1girl", "1": "solo"},
        "tag_to_category": {"1girl": "General", "solo": "General"},
    }
    p = tmp_path / "tag_mapping.json"
    p.write_text(json.dumps(mapping), encoding="utf-8")
    labels = load_tag_mapping(p)
    assert labels.names[0] == "1girl"
    assert len(labels.general) == 2
