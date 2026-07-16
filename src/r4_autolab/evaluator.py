from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .models import Comparison, RunSummary


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

