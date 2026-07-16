from __future__ import annotations

import json
from pathlib import Path
import tomllib
from typing import Any, Iterable

from .models import Comparison, RunSummary
from .analysis.cadence import analyze_cadence


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at line {line_number}: {error}") from error
            if not isinstance(value, dict):
                raise ValueError(f"JSONL line {line_number} is not an object")
            events.append(value)
    return events


def summarize_events(events: Iterable[dict[str, Any]]) -> RunSummary:
    values = list(events)
    if not values:
        raise ValueError("cannot summarize an empty trace")
    gpu_hashes = [str(event.get("gpu_hash", "")) for event in values]
    duplicate_count = sum(left == right for left, right in zip(gpu_hashes, gpu_hashes[1:]))
    duplicate_ratio = duplicate_count / max(1, len(gpu_hashes) - 1)
    last = values[-1]
    watches = dict(last.get("watch_values", {}))
    return RunSummary(
        vblanks=len(values),
        elapsed_seconds=float(last.get("monotonic_timestamp", len(values) / 60.0)),
        game_timer=float(last.get("game_timer", 0.0)),
        final_position=float(watches.get("position", 0.0)),
        final_speed=float(watches.get("speed", 0.0)),
        final_rpm=float(watches.get("rpm", 0.0)),
        unique_gpu_states=len(set(gpu_hashes)),
        duplicate_frame_ratio=duplicate_ratio,
        crashed=any(event.get("emulator_status") == "crashed" for event in values),
        frozen=duplicate_ratio >= 0.99,
        dropped_events=max(int(event.get("dropped_event_count", 0)) for event in values),
    )


def compare_summaries(
    baseline_id: str,
    experiment_id: str,
    baseline: RunSummary,
    experiment: RunSummary,
) -> Comparison:
    speed_ratio = experiment.game_timer / baseline.game_timer if baseline.game_timer else 0.0
    return Comparison(
        baseline_id=baseline_id,
        experiment_id=experiment_id,
        game_speed_ratio=speed_ratio,
        position_delta=experiment.final_position - baseline.final_position,
        speed_delta=experiment.final_speed - baseline.final_speed,
        rpm_delta=experiment.final_rpm - baseline.final_rpm,
        unique_gpu_state_delta=experiment.unique_gpu_states - baseline.unique_gpu_states,
        duplicate_ratio_delta=experiment.duplicate_frame_ratio - baseline.duplicate_frame_ratio,
        stable=not experiment.crashed and not experiment.frozen and experiment.dropped_events == 0,
    )


def summary_from_record(record: dict[str, Any]) -> RunSummary:
    value = record.get("summary")
    if not isinstance(value, dict):
        raise ValueError(f"run {record.get('id')} has no summary")
    return RunSummary(**value)


def trajectory_divergence(
    baseline_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    fields: tuple[str, ...] = ("position", "speed", "rpm"),
) -> dict[str, float]:
    baseline_by_vblank = {int(event["vblank_index"]): event for event in baseline_events}
    candidate_by_vblank = {int(event["vblank_index"]): event for event in candidate_events}
    common = sorted(baseline_by_vblank.keys() & candidate_by_vblank.keys())
    if not common:
        raise ValueError("traces have no common VBlank indexes")
    result: dict[str, float] = {}
    for field in fields:
        result[field] = max(
            abs(
                float(dict(baseline_by_vblank[index].get("watch_values", {})).get(field, 0.0))
                - float(dict(candidate_by_vblank[index].get("watch_values", {})).get(field, 0.0))
            )
            for index in common
        )
    return result


def evaluate_trace_pair(
    baseline_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    criteria_path: Path,
) -> dict[str, Any]:
    with criteria_path.open("rb") as handle:
        criteria = tomllib.load(handle)
    baseline = summarize_events(baseline_events)
    candidate = summarize_events(candidate_events)
    comparison = compare_summaries("baseline", "candidate", baseline, candidate)
    divergence = trajectory_divergence(baseline_events, candidate_events)
    timing = criteria["timing"]
    physics = criteria["physics"]
    rendering = criteria["rendering"]
    candidate_cadence = analyze_cadence(candidate_events, "gpu_hash")
    checks = {
        "game_speed_ratio": float(timing["game_speed_ratio_min"]) <= comparison.game_speed_ratio <= float(timing["game_speed_ratio_max"]),
        "position_divergence": divergence["position"] <= float(physics["max_position_delta"]),
        "speed_divergence": divergence["speed"] <= float(physics["max_speed_delta"]),
        "rpm_divergence": divergence["rpm"] <= float(physics["max_rpm_delta"]),
        "duplicate_ratio": candidate.duplicate_frame_ratio <= float(rendering["maximum_duplicate_ratio"]),
        "unique_states_per_second": candidate_cadence.update_hz >= float(rendering["minimum_unique_states_per_second"]),
        "stability": comparison.stable,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "comparison": comparison.to_dict(),
        "trajectory_max_delta": divergence,
        "baseline_cadence": analyze_cadence(baseline_events, "gpu_hash").to_dict(),
        "candidate_cadence": candidate_cadence.to_dict(),
    }
