import pytest

from r4_autolab.models import ExperimentProposal, PatchChange, TargetVersion
from r4_autolab.safety import PatchValidator, SafetyViolation


TARGET = TargetVersion("TEST", "a" * 64)


def change(**overrides: object) -> PatchChange:
    values = {
        "address": 0x80010000,
        "width": 4,
        "expected_original": b"\x00\x00\x00\x00",
        "replacement": b"\x01\x00\x00\x00",
        "evidence": ("trace-1",),
    }
    values.update(overrides)
    return PatchChange(**values)  # type: ignore[arg-type]


def test_valid_change_and_original_bytes() -> None:
    proposal = ExperimentProposal("x", "test", TARGET, (change(),))
    validator = PatchValidator()
    validator.validate_proposal(proposal, TARGET, {0x80010000})
    validator.verify_original(change(), b"\x00\x00\x00\x00")


@pytest.mark.parametrize(
    "candidate",
    [
        change(address=0x7FFFFFFC),
        change(address=0x80010001),
        change(evidence=()),
        change(replacement=b"\x00\x00\x00\x00"),
        change(width=3, expected_original=b"\0" * 3, replacement=b"\1" * 3),
    ],
)
def test_unsafe_change_is_rejected(candidate: PatchChange) -> None:
    with pytest.raises(SafetyViolation):
        PatchValidator().validate_change(candidate)


def test_target_and_original_mismatch_are_rejected() -> None:
    proposal = ExperimentProposal("x", "test", TARGET, (change(),))
    with pytest.raises(SafetyViolation):
        PatchValidator().validate_proposal(proposal, TargetVersion("OTHER", "b" * 64))
    with pytest.raises(SafetyViolation):
        PatchValidator().verify_original(change(), b"\xff" * 4)


def test_unsafe_artifact_id_is_rejected() -> None:
    proposal = ExperimentProposal("../escape", "test", TARGET)
    with pytest.raises(SafetyViolation, match="safe artifact"):
        PatchValidator().validate_proposal(proposal, TARGET)
