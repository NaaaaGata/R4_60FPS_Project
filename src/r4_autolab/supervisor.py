from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .emulator.base import EmulatorAdapter
from .evaluator import summarize_events
from .models import (
    ExperimentProposal,
    ExperimentState,
    LaunchConfig,
    RunSummary,
    TargetVersion,
)
from .safety import PatchValidator, SafetyViolation
from .state_machine import ExperimentStateMachine
from .storage import ExperimentStore


class ExperimentSupervisor:
    def __init__(
        self,
        store: ExperimentStore,
        emulator: EmulatorAdapter,
        runs_dir: Path,
        target: TargetVersion,
        *,
        timeout_seconds: float = 5.0,
        validator: PatchValidator | None = None,
    ) -> None:
        self.store = store
        self.emulator = emulator
        self.runs_dir = runs_dir
        self.target = target
        self.timeout_seconds = timeout_seconds
        self.validator = validator or PatchValidator()

    def _move(
        self,
        experiment_id: str,
        machine: ExperimentStateMachine,
        target: ExperimentState,
        detail: str | None = None,
    ) -> None:
        old = machine.state
        machine.transition(target)
        self.store.transition(experiment_id, old, target, detail)

    def run(
        self,
        proposal: ExperimentProposal,
        *,
        kind: str,
        scenario: str,
        vblanks: int,
        save_state: Path | None = None,
    ) -> RunSummary:
        if vblanks <= 0:
            raise ValueError("vblanks must be positive")
        # Validate before deriving or creating any filesystem path from agent-supplied data.
        self.validator.validate_artifact_id(proposal.id)
        run_dir = self.runs_dir / proposal.id
        if run_dir.exists():
            raise FileExistsError(f"run already exists: {run_dir}")
        run_dir.mkdir(parents=True)
        self.store.create(proposal, kind, scenario, run_dir)
        (run_dir / "proposal.json").write_text(
            json.dumps(proposal.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        machine = ExperimentStateMachine()
        applied: list[tuple[int, bytes]] = []
        launched = False
        try:
            self._move(proposal.id, machine, ExperimentState.VALIDATING)
            self.validator.validate_proposal(proposal, self.target)
            self._move(proposal.id, machine, ExperimentState.PREPARING)
            self._move(proposal.id, machine, ExperimentState.LAUNCHING)
            self.emulator.launch(LaunchConfig(scenario, run_dir, self.timeout_seconds))
            launched = True
            self.emulator.connect()
            self._move(proposal.id, machine, ExperimentState.LOADING_STATE)
            if save_state is not None:
                self.emulator.load_state(save_state)
            self._move(proposal.id, machine, ExperimentState.APPLYING_PATCH)
            for change in proposal.changes:
                original = self.emulator.read_memory(change.address, change.width)
                self.validator.verify_original(change, original)
                self.emulator.write_memory(change.address, change.replacement)
                applied.append((change.address, original))
            self._move(proposal.id, machine, ExperimentState.RUNNING)
            self.emulator.run_vblanks(vblanks)
            self._move(proposal.id, machine, ExperimentState.COLLECTING)
            events = self.emulator.drain_events()
            self.emulator.capture_screenshot(run_dir / "final.png")
            try:
                self.emulator.export_gpu_log(run_dir / "gpu.log")
            except NotImplementedError as error:
                (run_dir / "gpu.log.unsupported.txt").write_text(str(error) + "\n", encoding="utf-8")
            trace_path = run_dir / "telemetry.jsonl"
            with trace_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    event["experiment_id"] = proposal.id
                    handle.write(json.dumps(event, sort_keys=True) + "\n")
            self._move(proposal.id, machine, ExperimentState.RESTORING)
            for address, original in reversed(applied):
                self.emulator.write_memory(address, original)
            applied.clear()
            self._move(proposal.id, machine, ExperimentState.EVALUATING)
            summary = summarize_events(events)
            (run_dir / "summary.json").write_text(
                json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            self.store.complete(proposal.id, summary)
            self._move(proposal.id, machine, ExperimentState.COMPLETED)
            return summary
        except Exception as error:
            restoration_errors: list[str] = []
            if launched:
                for address, original in reversed(applied):
                    try:
                        self.emulator.write_memory(address, original)
                    except Exception as restore_error:
                        restoration_errors.append(str(restore_error))
            detail = str(error)
            if restoration_errors:
                detail += "; restoration failed: " + "; ".join(restoration_errors)
            self.store.set_error(proposal.id, detail)
            terminal = (
                ExperimentState.QUARANTINED
                if isinstance(error, SafetyViolation) or restoration_errors
                else ExperimentState.FAILED
            )
            if machine.state not in {ExperimentState.COMPLETED, terminal}:
                self._move(proposal.id, machine, terminal, detail)
            raise
        finally:
            if launched:
                self.emulator.shutdown()
