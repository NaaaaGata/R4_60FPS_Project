import json
from pathlib import Path

import pytest

from r4_autolab.loop_parity import (
    classify_loop_sample,
    load_branch_inventory,
    summarize_loop_samples,
)


def test_active_duplicate_classification_uses_bounded_markers() -> None:
    assert classify_loop_sample(["race_overlay"], False) == "active"
    assert classify_loop_sample([], False) == "duplicate"
    assert classify_loop_sample([], True) == "transition_without_active_marker"


def test_loop_summary_counts_branches_markers_and_transitions() -> None:
    samples = [
        {
            "classification": "active",
            "markers": ["race_overlay", "gpu_submit_a"],
            "branches": [{"address": "0x8001EC54", "taken": False}],
            "screenshot_changed": True,
        },
        {
            "classification": "duplicate",
            "markers": [],
            "branches": [{"address": "0x8001EC54", "taken": True}],
            "screenshot_changed": False,
        },
    ]
    summary = summarize_loop_samples(samples)
    assert summary["class_counts"] == {"active": 1, "duplicate": 1}
    assert summary["branch_outcomes"]["0x8001EC54"] == {"taken": 1, "not_taken": 1}
    assert summary["screenshot_transitions"] == 1


def test_branch_inventory_rejects_wrong_target_identity(tmp_path: Path) -> None:
    path = tmp_path / "branches.json"
    path.write_text(json.dumps({"protocol_version": 1, "executable_sha256": "a" * 64, "branches": []}))
    with pytest.raises(ValueError, match="identity"):
        load_branch_inventory(path, "b" * 64)
