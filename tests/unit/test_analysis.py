import json
from pathlib import Path

from r4_autolab.analysis.cadence import analyze_cadence
from r4_autolab.analysis.visual import analyze_raw_screenshot
from r4_autolab.evaluator import evaluate_trace_pair, trajectory_divergence


def events(render_every: int, position_offset: float = 0.0) -> list[dict[str, object]]:
    return [
        {
            "vblank_index": index,
            "monotonic_timestamp": index / 60,
            "game_timer": index / 60,
            "gpu_hash": f"gpu-{index // render_every}",
            "watch_values": {"position": index / 2 + position_offset, "speed": 100, "rpm": 4000},
            "dropped_event_count": 0,
        }
        for index in range(1, 121)
    ]


def test_cadence_and_trajectory_analysis() -> None:
    baseline = events(2)
    candidate = events(1)
    cadence = analyze_cadence(candidate, "gpu_hash")
    assert cadence.update_hz > 59
    assert cadence.duplicate_ratio == 0
    assert trajectory_divergence(baseline, candidate) == {"position": 0.0, "speed": 0.0, "rpm": 0.0}


def test_evaluation_profile_passes_render_only_candidate(tmp_path: Path) -> None:
    criteria = tmp_path / "criteria.toml"
    criteria.write_text(
        """[timing]
game_speed_ratio_min=0.98
game_speed_ratio_max=1.02
[physics]
max_position_delta=0.01
max_speed_delta=0.01
max_rpm_delta=1.0
[rendering]
minimum_unique_states_per_second=58
maximum_duplicate_ratio=0.05
""",
        encoding="utf-8",
    )
    assert evaluate_trace_pair(events(2), events(1), criteria)["passed"] is True


def test_raw_visual_analysis_checks_size_and_black_ratio(tmp_path: Path) -> None:
    raw = tmp_path / "frame.raw"
    metadata = tmp_path / "frame.json"
    raw.write_bytes(b"\0\0" * 4)
    metadata.write_text(json.dumps({"width": 2, "height": 2, "bits_per_pixel": 16}), encoding="utf-8")
    stats = analyze_raw_screenshot(raw, metadata)
    assert stats.valid_size
    assert stats.black_pixel_ratio == 1.0
