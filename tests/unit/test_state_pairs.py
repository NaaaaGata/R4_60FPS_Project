from __future__ import annotations

import pytest

from r4_autolab.state_pairs import compare_state_pair


def test_compares_same_and_previous_frame_state() -> None:
    samples = [
        {"current": 1, "candidate": 1},
        {"current": 2, "candidate": 1},
        {"current": 3, "candidate": 2},
    ]
    result = compare_state_pair(samples, "current", "candidate")
    assert result["same_frame_ratio"] == pytest.approx(1 / 3)
    assert result["previous_frame_ratio"] == 1.0


def test_state_pair_comparison_rejects_empty_samples() -> None:
    with pytest.raises(ValueError, match="needs samples"):
        compare_state_pair([], "a", "b")
