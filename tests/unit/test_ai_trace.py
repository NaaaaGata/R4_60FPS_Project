from __future__ import annotations

import pytest

from r4_autolab.ai_trace import PLAYER_OBJECT, decode_vehicle, trajectory_signature, validate_vehicle_pointers


def test_validates_player_first_unique_aligned_vehicle_pointers() -> None:
    validate_vehicle_pointers(3, [PLAYER_OBJECT, 0x800AC100, 0x800AC500])
    with pytest.raises(ValueError, match="first vehicle"):
        validate_vehicle_pointers(2, [0x800AC100, PLAYER_OBJECT])
    with pytest.raises(ValueError, match="duplicates"):
        validate_vehicle_pointers(2, [PLAYER_OBJECT, PLAYER_OBJECT])
    with pytest.raises(ValueError, match="invalid vehicle"):
        validate_vehicle_pointers(2, [PLAYER_OBJECT, 0x80200000])


def test_decodes_fixed_vehicle_fields() -> None:
    data = bytearray(0x2AC - 0x10)
    data[0:4] = (-4).to_bytes(4, "little", signed=True)
    data[0x1D8 - 0x10:0x1DA - 0x10] = (777).to_bytes(2, "little")
    result = decode_vehicle(PLAYER_OBJECT, bytes(data))
    assert result["x"] == -4
    assert result["speed_related"] == 777


def test_trajectory_signature_ignores_attempt_metadata() -> None:
    samples = [{"relative_vblank": 2, "vehicles": [{"x": 1}]}]
    assert trajectory_signature(samples) == [{"relative_vblank": 2, "vehicles": [{"x": 1}]}]
