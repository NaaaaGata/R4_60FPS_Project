from pathlib import Path

from r4_autolab.models import ExperimentProposal, ExperimentState, TargetVersion
from r4_autolab.storage import ExperimentStore


def test_store_persists_creation_and_transition(tmp_path: Path) -> None:
    proposal = ExperimentProposal("run-1", "baseline", TargetVersion("FAKE", "0" * 64))
    with ExperimentStore(tmp_path / "runs.sqlite3") as store:
        store.create(proposal, "baseline", "scenario", tmp_path / "run-1")
        store.transition("run-1", ExperimentState.CREATED, ExperimentState.VALIDATING)
        record = store.get("run-1")
        assert record["state"] == "VALIDATING"
        assert store.transitions("run-1") == ["CREATED", "VALIDATING"]

