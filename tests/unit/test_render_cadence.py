import pytest

from r4_autolab.render_cadence import summarize_render_hashes


def test_render_hash_summary_detects_two_vblank_runs() -> None:
    result = summarize_render_hashes(["a", "a", "b", "b", "c", "c"])
    assert result["samples"] == 6
    assert result["unique_hashes"] == 3
    assert result["changes"] == 2
    assert result["duplicate_transition_ratio"] == pytest.approx(0.6)
    assert result["estimated_change_hz_at_ntsc"] == pytest.approx(23.976)
    assert result["run_lengths"] == [2, 2, 2]


def test_render_hash_summary_requires_an_interval() -> None:
    with pytest.raises(ValueError, match="at least two"):
        summarize_render_hashes(["a"])
