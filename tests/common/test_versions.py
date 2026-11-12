from mulebox.common import versions


def test_parse_and_compare():
    assert versions.parse("0.82.0") == (0, 82, 0)
    assert versions.parse("0.82") is None and versions.parse(None) is None
    assert versions.compare("0.9.0", "0.10.0") == -1  # numbers, not text
    assert versions.compare("1.0.0", "1.0.0") == 0
    assert versions.compare("0.82.1", "0.82.0") == 1
    assert versions.compare("dev", "0.82.0") is None


def test_same_release_ignores_trailing_zeros():
    assert versions.same_release("16.2", "16.2.0") and versions.same_release("16", "16.0.0")
    assert versions.same_release("16.02", "16.2")
    assert not versions.same_release("16.2", "16.20")
    assert not versions.same_release("16.2", "16.2.1")
    assert not versions.same_release("16.0", "1.6")
