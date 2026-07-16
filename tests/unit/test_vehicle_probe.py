from __future__ import annotations

import pytest

from r4_autolab.vehicle_probe import PLAYER_OBJECT_SIZE, SPEED_OFFSET, pearson, rank_object_fields


def test_pearson_handles_correlation_and_constants() -> None:
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 1, 1], [2, 3, 4]) is None


def test_ranks_only_bounded_player_object_fields() -> None:
    samples = []
    for value in range(8):
        data = bytearray(PLAYER_OBJECT_SIZE)
        data[SPEED_OFFSET:SPEED_OFFSET + 2] = value.to_bytes(2, "little")
        data[0x200:0x202] = (value * 2).to_bytes(2, "little")
        samples.append(bytes(data))
    ranked = rank_object_fields(samples, limit=8)
    assert ranked[0]["speed_correlation"] == pytest.approx(1.0)
    assert all(0 <= int(item["offset"], 0) < PLAYER_OBJECT_SIZE for item in ranked)


def test_rejects_unbounded_or_wrong_sized_object_samples() -> None:
    with pytest.raises(ValueError, match="0x400"):
        rank_object_fields([bytes(PLAYER_OBJECT_SIZE + 1)])
