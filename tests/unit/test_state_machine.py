import pytest

from r4_autolab.models import ExperimentState
from r4_autolab.state_machine import ExperimentStateMachine, InvalidTransition


def test_happy_path_reaches_completed() -> None:
    machine = ExperimentStateMachine()
    for state in (
        ExperimentState.VALIDATING,
        ExperimentState.PREPARING,
        ExperimentState.LAUNCHING,
        ExperimentState.LOADING_STATE,
        ExperimentState.APPLYING_PATCH,
        ExperimentState.RUNNING,
        ExperimentState.COLLECTING,
        ExperimentState.RESTORING,
        ExperimentState.EVALUATING,
        ExperimentState.COMPLETED,
    ):
        machine.transition(state)
    assert machine.state == ExperimentState.COMPLETED


def test_invalid_transition_is_rejected() -> None:
    machine = ExperimentStateMachine()
    with pytest.raises(InvalidTransition):
        machine.transition(ExperimentState.RUNNING)


def test_failure_is_allowed_from_non_terminal_state() -> None:
    machine = ExperimentStateMachine()
    machine.transition(ExperimentState.FAILED)
    with pytest.raises(InvalidTransition):
        machine.transition(ExperimentState.VALIDATING)

