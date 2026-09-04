from siftivex.ids import content_hash, image_id_from_hash


def test_image_id_format(tmp_path):
    f = tmp_path / "test.png"
    f.write_bytes(b"\x89PNG dummy")
    h = content_hash(f)
    assert len(h) == 64
    iid = image_id_from_hash(h)
    assert iid.startswith("img_")
    assert len(iid) == 4 + 16
