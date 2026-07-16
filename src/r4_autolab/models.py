from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ExperimentState(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    PREPARING = "PREPARING"
    LAUNCHING = "LAUNCHING"
    LOADING_STATE = "LOADING_STATE"
    APPLYING_PATCH = "APPLYING_PATCH"
    RUNNING = "RUNNING"
    COLLECTING = "COLLECTING"
    RESTORING = "RESTORING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    ABORTED = "ABORTED"
    QUARANTINED = "QUARANTINED"


TERMINAL_STATES = {
    ExperimentState.COMPLETED,
    ExperimentState.FAILED,
    ExperimentState.TIMED_OUT,
    ExperimentState.ABORTED,
    ExperimentState.QUARANTINED,
}


@dataclass(frozen=True)
class TargetVersion:
    serial: str
    executable_sha256: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TargetVersion:
        return cls(str(value.get("serial", "")), str(value.get("executable_sha256", "")))


@dataclass(frozen=True)
class PatchChange:
    address: int
    width: int
    expected_original: bytes
    replacement: bytes
    instruction_before: str = "unknown"
    instruction_after: str = "unknown"
    evidence: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PatchChange:
        raw_address = value["address"]
        address = int(raw_address, 0) if isinstance(raw_address, str) else int(raw_address)
        return cls(
            address=address,
            width=int(value["width"]),
            expected_original=bytes.fromhex(str(value["expected_original_hex"])),
            replacement=bytes.fromhex(str(value["replacement_hex"])),
            instruction_before=str(value.get("instruction_before", "unknown")),
            instruction_after=str(value.get("instruction_after", "unknown")),
            evidence=tuple(str(item) for item in value.get("evidence", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": f"0x{self.address:08X}",
            "width": self.width,
            "expected_original_hex": self.expected_original.hex(),
            "replacement_hex": self.replacement.hex(),
            "instruction_before": self.instruction_before,
            "instruction_after": self.instruction_after,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ExperimentProposal:
    id: str
    hypothesis: str
    target_version: TargetVersion
    changes: tuple[PatchChange, ...] = ()
    predicted_effects: dict[str, Any] = field(default_factory=dict)
    stop_conditions: tuple[str, ...] = ()
    evaluation_profile: str = "default"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ExperimentProposal:
        return cls(
            id=str(value["id"]),
            hypothesis=str(value["hypothesis"]),
            target_version=TargetVersion.from_dict(value["target_version"]),
            changes=tuple(PatchChange.from_dict(item) for item in value.get("changes", [])),
            predicted_effects=dict(value.get("predicted_effects", {})),
            stop_conditions=tuple(str(item) for item in value.get("stop_conditions", [])),
            evaluation_profile=str(value.get("evaluation_profile", "default")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hypothesis": self.hypothesis,
            "target_version": asdict(self.target_version),
            "changes": [change.to_dict() for change in self.changes],
            "predicted_effects": self.predicted_effects,
            "stop_conditions": list(self.stop_conditions),
            "evaluation_profile": self.evaluation_profile,
        }


@dataclass(frozen=True)
class LaunchConfig:
    scenario: str
    run_dir: Path
    timeout_seconds: float


@dataclass(frozen=True)
class BreakpointSpec:
    address: int
    access: str
    width: int = 4
    max_hits: int | None = None


@dataclass(frozen=True)
class RegisterSnapshot:
    pc: int
    ra: int
    sp: int
    gprs: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RunSummary:
    vblanks: int
    elapsed_seconds: float
    game_timer: float
    final_position: float
    final_speed: float
    final_rpm: float
    unique_gpu_states: int
    duplicate_frame_ratio: float
    crashed: bool = False
    frozen: bool = False
    dropped_events: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Comparison:
    baseline_id: str
    experiment_id: str
    game_speed_ratio: float
    position_delta: float
    speed_delta: float
    rpm_delta: float
    unique_gpu_state_delta: int
    duplicate_ratio_delta: float
    stable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
