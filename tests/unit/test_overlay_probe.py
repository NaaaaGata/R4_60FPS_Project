from r4_autolab.overlay_probe import find_fingerprint


def test_fingerprint_search_is_exact_bounded_and_supports_multiple_matches() -> None:
    assert find_fingerprint(b"xxABCDyyABCDzz", b"ABCD") == [2, 8]
    assert find_fingerprint(b"AAAA", b"AA", max_matches=2) == [0, 1]
