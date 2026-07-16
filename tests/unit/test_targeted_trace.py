import pytest

from r4_autolab.targeted_trace import TargetWatch, parse_target_watch


def test_parse_target_watch() -> None:
    assert parse_target_watch("race_tick:0x800F2BC4:4") == TargetWatch(
        "race_tick", 0x800F2BC4, 4
    )


def test_parse_target_watch_rejects_unsafe_range() -> None:
    with pytest.raises(ValueError, match="main RAM"):
        parse_target_watch("bad:0x80200000:4")
