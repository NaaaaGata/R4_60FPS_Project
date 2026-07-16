from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


CLASSIFICATIONS = frozenset({
    "SAFE_RENDER_BOUNDARY",
    "POSSIBLE_WITH_STATE_SHADOWING",
    "POSSIBLE_WITH_INTERPOLATION",
    "UNSAFE_SHARED_LOGIC",
    "INSUFFICIENT_EVIDENCE",
})
CONFIDENCE = frozenset({"low", "medium", "high"})
REQUIRED_FIELDS = frozenset({
    "candidate", "address", "role", "cadence", "required_inputs", "writes",
    "unsafe_side_effects", "gpu_relationship", "buffer_relationship",
    "can_reinvoke_without_logic", "can_use_interpolated_state", "confidence",
    "blocking_evidence", "supporting_evidence", "classification",
})


@dataclass(frozen=True)
class RenderBoundaryCandidate:
    candidate: str
    address: str
    role: str
    cadence: str
    required_inputs: tuple[str, ...]
    writes: tuple[str, ...]
    unsafe_side_effects: tuple[str, ...]
    gpu_relationship: str
    buffer_relationship: str
    can_reinvoke_without_logic: bool
    can_use_interpolated_state: bool
    confidence: str
    blocking_evidence: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    classification: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RenderBoundaryCandidate:
        if set(value) != REQUIRED_FIELDS:
            missing = sorted(REQUIRED_FIELDS - set(value))
            extra = sorted(set(value) - REQUIRED_FIELDS)
            raise ValueError(f"candidate fields mismatch missing={missing} extra={extra}")
        for name in (
            "candidate", "address", "role", "cadence", "gpu_relationship",
            "buffer_relationship", "confidence", "classification",
        ):
            if not isinstance(value[name], str) or not value[name]:
                raise ValueError(f"candidate field {name} must be a non-empty string")
        if not re.fullmatch(r"0x[0-9A-F]{8}", value["address"]):
            raise ValueError("candidate address must be uppercase 32-bit hex")
        if value["confidence"] not in CONFIDENCE:
            raise ValueError("invalid candidate confidence")
        if value["classification"] not in CLASSIFICATIONS:
            raise ValueError("invalid candidate classification")
        arrays: dict[str, tuple[str, ...]] = {}
        for name in (
            "required_inputs", "writes", "unsafe_side_effects",
            "blocking_evidence", "supporting_evidence",
        ):
            raw = value[name]
            if not isinstance(raw, list) or any(not isinstance(item, str) or not item for item in raw):
                raise ValueError(f"candidate field {name} must be an array of non-empty strings")
            arrays[name] = tuple(raw)
        for name in ("can_reinvoke_without_logic", "can_use_interpolated_state"):
            if not isinstance(value[name], bool):
                raise ValueError(f"candidate field {name} must be boolean")
        return cls(
            candidate=value["candidate"], address=value["address"], role=value["role"],
            cadence=value["cadence"], required_inputs=arrays["required_inputs"],
            writes=arrays["writes"], unsafe_side_effects=arrays["unsafe_side_effects"],
            gpu_relationship=value["gpu_relationship"], buffer_relationship=value["buffer_relationship"],
            can_reinvoke_without_logic=value["can_reinvoke_without_logic"],
            can_use_interpolated_state=value["can_use_interpolated_state"],
            confidence=value["confidence"], blocking_evidence=arrays["blocking_evidence"],
            supporting_evidence=arrays["supporting_evidence"], classification=value["classification"],
        )


def load_candidate_report(value: dict[str, Any]) -> tuple[str, tuple[RenderBoundaryCandidate, ...]]:
    if set(value) != {"protocol_version", "result", "candidates"} or value["protocol_version"] != 1:
        raise ValueError("render candidate report must use exact protocol_version 1 envelope")
    result = value["result"]
    if result not in {"RESULT_A", "RESULT_B", "RESULT_C"}:
        raise ValueError("invalid overall render-boundary result")
    raw = value["candidates"]
    if not isinstance(raw, list) or not raw:
        raise ValueError("render candidate report needs a non-empty candidates array")
    candidates = tuple(RenderBoundaryCandidate.from_dict(dict(item)) for item in raw if isinstance(item, dict))
    if len(candidates) != len(raw):
        raise ValueError("invalid non-object render candidate")
    if result == "RESULT_A" and not any(item.classification == "SAFE_RENDER_BOUNDARY" for item in candidates):
        raise ValueError("RESULT_A requires a SAFE_RENDER_BOUNDARY candidate")
    return result, candidates
