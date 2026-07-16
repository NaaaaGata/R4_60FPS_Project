from __future__ import annotations

from dataclasses import dataclass

from .models import ExperimentState, TERMINAL_STATES


class InvalidTransition(ValueError):
    pass


_NORMAL_NEXT: dict[ExperimentState, ExperimentState] = {
    ExperimentState.CREATED: ExperimentState.VALIDATING,
    ExperimentState.VALIDATING: ExperimentState.PREPARING,
    ExperimentState.PREPARING: ExperimentState.LAUNCHING,
    ExperimentState.LAUNCHING: ExperimentState.LOADING_STATE,
    ExperimentState.LOADING_STATE: ExperimentState.APPLYING_PATCH,
    ExperimentState.APPLYING_PATCH: ExperimentState.RUNNING,
    ExperimentState.RUNNING: ExperimentState.COLLECTING,
    ExperimentState.COLLECTING: ExperimentState.RESTORING,
    ExperimentState.RESTORING: ExperimentState.EVALUATING,
    ExperimentState.EVALUATING: ExperimentState.COMPLETED,
}


@dataclass
class ExperimentStateMachine:
    state: ExperimentState = ExperimentState.CREATED

    def transition(self, target: ExperimentState) -> None:
        if self.state in TERMINAL_STATES:
            raise InvalidTransition(f"terminal state {self.state} cannot transition")
        if target in {
            ExperimentState.FAILED,
            ExperimentState.TIMED_OUT,
            ExperimentState.ABORTED,
            ExperimentState.QUARANTINED,
        }:
            self.state = target
            return
        expected = _NORMAL_NEXT.get(self.state)
        if target != expected:
            raise InvalidTransition(f"expected {expected}, got {target}")
        self.state = target

