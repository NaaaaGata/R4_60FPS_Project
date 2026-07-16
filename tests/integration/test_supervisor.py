from pathlib import Path

import pytest

from r4_autolab.emulator.fake import FakeEmulator
from r4_autolab.models import ExperimentProposal, PatchChange, TargetVersion
from r4_autolab.safety import SafetyViolation
from r4_autolab.storage import ExperimentStore
from r4_autolab.supervisor import ExperimentSupervisor


TARGET = TargetVersion("FAKE", "0" * 64)


def candidate(run_id: str, expected: bytes = b"\0" * 4) -> ExperimentProposal:
    return ExperimentProposal(
        run_id,
        "render every VBlank",
        TARGET,
        (
            PatchChange(
                FakeEmulator.PATCH_ADDRESS,
                4,
                expected,
                b"\x01\0\0\0",
                evidence=("fake-contract",),
            ),
        ),
    )


def test_fake_experiment_writes_trace_restores_patch_and_records_states(tmp_path: Path) -> None:
    emulator = FakeEmulator()
    with ExperimentStore(tmp_path / "runs.sqlite3") as store:
        supervisor = ExperimentSupervisor(store, emulator, tmp_path / "runs", TARGET)
        summary = supervisor.run(candidate("candidate-1"), kind="candidate", scenario="test", vblanks=120)
        assert summary.unique_gpu_states == 120
        assert summary.duplicate_frame_ratio == 0
        assert emulator.read_memory(FakeEmulator.PATCH_ADDRESS, 4) == b"\0" * 4
        assert store.get("candidate-1")["state"] == "COMPLETED"
        assert store.transitions("candidate-1") == [
            "CREATED", "VALIDATING", "PREPARING", "LAUNCHING", "LOADING_STATE",
            "APPLYING_PATCH", "RUNNING", "COLLECTING", "RESTORING", "EVALUATING", "COMPLETED",
        ]
    assert (tmp_path / "runs/candidate-1/telemetry.jsonl").read_text().count("\n") == 120
    assert (tmp_path / "runs/candidate-1/final.png").read_bytes().startswith(b"\x89PNG")
    assert (tmp_path / "runs/candidate-1/gpu.log").exists()


def test_original_byte_mismatch_is_quarantined(tmp_path: Path) -> None:
    emulator = FakeEmulator()
    with ExperimentStore(tmp_path / "runs.sqlite3") as store:
        supervisor = ExperimentSupervisor(store, emulator, tmp_path / "runs", TARGET)
        with pytest.raises(SafetyViolation, match="original bytes mismatch"):
            supervisor.run(
                candidate("bad-original", b"\xff" * 4),
                kind="candidate",
                scenario="test",
                vblanks=10,
            )
        assert store.get("bad-original")["state"] == "QUARANTINED"


class ReachableFailureEmulator(FakeEmulator):
    def run_vblanks(self, count: int) -> None:
        raise RuntimeError("injected run failure")


def test_patch_is_restored_after_run_failure(tmp_path: Path) -> None:
    emulator = ReachableFailureEmulator()
    with ExperimentStore(tmp_path / "runs.sqlite3") as store:
        supervisor = ExperimentSupervisor(store, emulator, tmp_path / "runs", TARGET)
        with pytest.raises(RuntimeError, match="injected"):
            supervisor.run(candidate("failed-run"), kind="candidate", scenario="test", vblanks=10)
        assert emulator.read_memory(FakeEmulator.PATCH_ADDRESS, 4) == b"\0" * 4
        assert store.get("failed-run")["state"] == "FAILED"


def test_unsafe_id_is_rejected_before_artifact_creation(tmp_path: Path) -> None:
    emulator = FakeEmulator()
    proposal = ExperimentProposal("../escape", "bad id", TARGET)
    with ExperimentStore(tmp_path / "runs.sqlite3") as store:
        supervisor = ExperimentSupervisor(store, emulator, tmp_path / "runs", TARGET)
        with pytest.raises(SafetyViolation, match="safe artifact"):
            supervisor.run(proposal, kind="candidate", scenario="test", vblanks=1)
    assert not (tmp_path / "escape").exists()
