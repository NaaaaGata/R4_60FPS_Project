import json
from pathlib import Path

from r4_autolab.campaign import CampaignBudget, CampaignRunner
from r4_autolab.codex_client import FakeCodexClient
from r4_autolab.emulator.fake import FakeEmulator
from r4_autolab.models import ExperimentProposal, PatchChange, TargetVersion
from r4_autolab.storage import ExperimentStore
from r4_autolab.supervisor import ExperimentSupervisor


def test_fake_campaign_records_budget_result_and_resume(tmp_path: Path) -> None:
    target = TargetVersion("FAKE", "0" * 64)
    baseline = ExperimentProposal("campaign-base", "base", target)
    candidate = ExperimentProposal(
        "campaign-candidate",
        "candidate",
        target,
        (PatchChange(0x80010000, 4, b"\0" * 4, b"\1\0\0\0", evidence=("fake",)),),
    )
    budget = CampaignBudget(2, 60, 2, 1, 1, 10000000, 120, 1, 1, 0.0)
    with ExperimentStore(tmp_path / "runs.sqlite3") as store:
        supervisor = ExperimentSupervisor(store, FakeEmulator(), tmp_path / "runs", target)
        runner = CampaignRunner(store, supervisor, FakeCodexClient([candidate]), budget, tmp_path / "campaign")
        report = runner.run(baseline, "fake", 120)
        assert report["results"][0]["comparison"]["game_speed_ratio"] == 1.0
        resumed = runner.run(baseline, "fake", 120)
        assert resumed == report
        assert store.get_campaign("campaign")["status"] == "COMPLETED"  # type: ignore[index]
    assert json.loads((tmp_path / "campaign/campaign.json").read_text())["stop_reason"] == "fake_client_exhausted"
