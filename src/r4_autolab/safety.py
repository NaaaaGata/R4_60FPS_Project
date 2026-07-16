from __future__ import annotations

import re

from .models import ExperimentProposal, PatchChange, TargetVersion


class SafetyViolation(ValueError):
    pass


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PatchValidator:
    RAM_START = 0x80000000
    RAM_END = 0x80200000

    def __init__(self, max_changes: int = 1) -> None:
        self.max_changes = max_changes

    def validate_proposal(
        self,
        proposal: ExperimentProposal,
        target: TargetVersion,
        executed_addresses: set[int] | None = None,
    ) -> None:
        self.validate_artifact_id(proposal.id)
        if not proposal.hypothesis.strip():
            raise SafetyViolation("proposal hypothesis must not be empty")
        if proposal.target_version != target:
            raise SafetyViolation("proposal target version does not match configured target")
        if proposal.changes and not _SHA256.fullmatch(target.executable_sha256):
            raise SafetyViolation("a verified 64-character executable SHA-256 is required for patching")
        if len(proposal.changes) > self.max_changes:
            raise SafetyViolation(f"at most {self.max_changes} change is allowed")
        for change in proposal.changes:
            self.validate_change(change, executed_addresses)

    def validate_artifact_id(self, artifact_id: str) -> None:
        if not _SAFE_ID.fullmatch(artifact_id) or ".." in artifact_id:
            raise SafetyViolation("proposal id is not a safe artifact identifier")

    def validate_change(self, change: PatchChange, executed_addresses: set[int] | None = None) -> None:
        if change.width not in {1, 2, 4}:
            raise SafetyViolation("patch width must be 1, 2, or 4")
        if len(change.expected_original) != change.width or len(change.replacement) != change.width:
            raise SafetyViolation("patch byte lengths must equal width")
        if change.expected_original == change.replacement:
            raise SafetyViolation("replacement must differ from original bytes")
        if not self.RAM_START <= change.address < self.RAM_END:
            raise SafetyViolation("patch address is outside PS1 main RAM")
        if change.address + change.width > self.RAM_END:
            raise SafetyViolation("patch crosses the PS1 main RAM boundary")
        if change.address % change.width:
            raise SafetyViolation("patch address is not naturally aligned")
        if not change.evidence:
            raise SafetyViolation("patch requires at least one evidence reference")
        if executed_addresses is not None and change.address not in executed_addresses:
            raise SafetyViolation("patch address was not observed executing")

    def verify_original(self, change: PatchChange, actual: bytes) -> None:
        if actual != change.expected_original:
            raise SafetyViolation(
                f"original bytes mismatch at 0x{change.address:08X}: "
                f"expected {change.expected_original.hex()}, got {actual.hex()}"
            )
