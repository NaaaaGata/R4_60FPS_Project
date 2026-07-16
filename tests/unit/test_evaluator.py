from r4_autolab.evaluator import compare_summaries, summarize_events


def events(render_every: int) -> list[dict[str, object]]:
    return [
        {
            "monotonic_timestamp": index / 60,
            "game_timer": index / 60,
            "gpu_hash": f"gpu-{index // render_every}",
            "watch_values": {"position": index / 2, "speed": 100, "rpm": 4000},
            "dropped_event_count": 0,
        }
        for index in range(1, 121)
    ]


def test_summary_and_comparison_detect_render_only_improvement() -> None:
    baseline = summarize_events(events(2))
    candidate = summarize_events(events(1))
    comparison = compare_summaries("base", "candidate", baseline, candidate)
    assert baseline.duplicate_frame_ratio > 0.49
    assert candidate.duplicate_frame_ratio == 0
    assert comparison.game_speed_ratio == 1
    assert comparison.position_delta == 0
    assert comparison.unique_gpu_state_delta == 59
    assert comparison.stable

