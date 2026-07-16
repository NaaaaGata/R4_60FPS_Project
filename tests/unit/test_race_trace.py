from r4_autolab.race_trace import (
    RACE_BREAKPOINT_PHASES,
    enrich_breakpoint_event,
    summarize_breakpoint_events,
)


def test_race_breakpoint_phase_order_matches_research_protocol() -> None:
    assert [phase[0] for phase in RACE_BREAKPOINT_PHASES] == [
        "frame-write",
        "player-xyz-write",
        "speed-write",
        "rpm-write",
        "heading-write",
        "camera-write",
        "player-xyz-read",
        "camera-read",
    ]


def test_breakpoint_event_records_identity_and_explicit_value_limitation() -> None:
    event = enrich_breakpoint_event(
        {
            "access": "write",
            "accessed_address": 0x800AC064,
            "access_width": 4,
            "pc": 0x80012340,
            "ra": 0x80011110,
            "sp": 0x801FFF00,
            "gprs": {"a0": 1},
            "vblank_index": 10,
            "cpu_cycles": 20,
        },
        phase="frame-write",
        scenario="accelerate",
        state_sha256="state",
        input_sha256="input",
    )
    assert event["old_value"] is None
    assert event["new_value"] is None
    assert event["gprs"] == {"a0": 1}
    assert "does not expose" in event["value_limitation"]
    assert summarize_breakpoint_events([event])[0]["pc"] == "0x80012340"
