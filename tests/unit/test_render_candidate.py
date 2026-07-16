from __future__ import annotations

import json
from pathlib import Path

import pytest

from r4_autolab.render_candidate import RenderBoundaryCandidate, load_candidate_report


def candidate() -> dict[str, object]:
    return {
        "candidate": "overlay", "address": "0x80114780", "role": "integrated",
        "cadence": "30Hz", "required_inputs": ["race state"], "writes": ["vehicle state"],
        "unsafe_side_effects": ["physics"], "gpu_relationship": "builds OT",
        "buffer_relationship": "uses active command arena", "can_reinvoke_without_logic": False,
        "can_use_interpolated_state": False, "confidence": "high",
        "blocking_evidence": ["physics write"], "supporting_evidence": ["30-frame trace"],
        "classification": "UNSAFE_SHARED_LOGIC",
    }


def test_validates_candidate_report_and_repository_artifact() -> None:
    value = {"protocol_version": 1, "result": "RESULT_C", "candidates": [candidate()]}
    result, candidates = load_candidate_report(value)
    assert result == "RESULT_C"
    assert candidates[0].address == "0x80114780"
    artifact = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/R4_RENDER_BOUNDARY_CANDIDATES.json").read_text()
    )
    assert load_candidate_report(artifact)[0] == "RESULT_C"


def test_rejects_missing_or_extra_candidate_fields() -> None:
    value = candidate()
    value.pop("writes")
    with pytest.raises(ValueError, match="fields mismatch"):
        RenderBoundaryCandidate.from_dict(value)


def test_result_a_requires_safe_candidate() -> None:
    with pytest.raises(ValueError, match="requires"):
        load_candidate_report({"protocol_version": 1, "result": "RESULT_A", "candidates": [candidate()]})
