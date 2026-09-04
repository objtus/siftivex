from siftivex.filename_tags import parse_legacy_filename_tags


def test_img_prefix():
    assert parse_legacy_filename_tags("IMG3078_2D-背景-空.JPG") == ["2D", "背景", "空"]


def test_img_underscore_id():
    assert parse_legacy_filename_tags("IMG_0265-建物-夕方-横.JPG") == ["建物", "夕方", "横"]


def test_numeric_prefix():
    assert parse_legacy_filename_tags("15283_1-風景-山-雲.jpg") == ["風景", "山", "雲"]


def test_no_tags():
    assert parse_legacy_filename_tags("IMG3214.JPG") == []
