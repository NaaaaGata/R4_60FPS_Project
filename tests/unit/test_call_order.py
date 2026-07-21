from __future__ import annotations

import pytest

from r4_autolab.call_order import (
    FUNCTION_EVIDENCE,
    reconstruct_call_order,
    render_only_eligible,
)


def event(address: int, cycles: int, ra: int = 0x80115000) -> dict[str, int]:
    return {
        "accessed_address": address,
        "cpu_cycles": cycles,
        "vblank_index": 10,
        "pc": address,
        "ra": ra,
    }


def test_reconstructs_order_by_cycle_and_overlay_boundary() -> None:
    events = [
        event(0x8003C838, 110),
        event(0x80114780, 100),
        event(0x80034178, 130),
        event(0x80038338, 120),
        event(0x8009331C, 140, 0x8001EC78),
        event(0x80114780, 200),
        event(0x8003C838, 210),
    ]
    frames = reconstruct_call_order(events, requested_frames=2, max_events_per_frame=16)
    assert [item["function"] for item in frames[0]["sequence"]] == [
        "race_overlay", "lap_timer", "vehicle_dispatcher", "camera_update", "gpu_submission_start"
    ]
    assert frames[0]["sequence"][-1]["caller"] == "0x8001EC70"
    assert frames[0]["sequence"][0]["depth_estimate"] == 0


def test_enforces_per_frame_event_bound() -> None:
    events = [event(0x80114780, 1)] + [event(0x8003C838, cycle) for cycle in range(2, 19)]
    with pytest.raises(RuntimeError, match="exceeded event bound"):
        reconstruct_call_order(events, requested_frames=1, max_events_per_frame=16)


def test_side_effect_classification_rejects_unsafe_render_candidates() -> None:
    assert not render_only_eligible(FUNCTION_EVIDENCE[0x8003C838])
    assert not render_only_eligible(FUNCTION_EVIDENCE[0x80074680])
    assert not render_only_eligible(FUNCTION_EVIDENCE[0x80034178])
    assert render_only_eligible(FUNCTION_EVIDENCE[0x80020E54])
