from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Any

from .codex_client import CodexClient, ResearchContext
from .evaluator import compare_summaries
from .models import ExperimentProposal
from .storage import ExperimentStore
from .supervisor import ExperimentSupervisor


@dataclass(frozen=True)
class CampaignBudget:
    max_experiments: int
    max_seconds: float
    max_codex_calls: int
    max_consecutive_crashes: int
    max_consecutive_no_progress: int
    max_storage_bytes: int
    max_vblanks_per_experiment: int
    max_changes_per_experiment: int
    max_retries_per_candidate: int
    max_cost: float

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CampaignBudget:
        return cls(**{field: value[field] for field in cls.__dataclass_fields__})


class CampaignRunner:
    def __init__(
        self,
        store: ExperimentStore,
        supervisor: ExperimentSupervisor,
        client: CodexClient,
        budget: CampaignBudget,
        output_directory: Path,
    ) -> None:
        self.store = store
        self.supervisor = supervisor
        self.client = client
        self.budget = budget
        self.output_directory = output_directory

    def run(self, baseline: ExperimentProposal, scenario: str, vblanks: int) -> dict[str, Any]:
        started = time.monotonic()
        campaign_id = self.output_directory.name
        previous = self.store.get_campaign(campaign_id)
        if previous is not None and previous["status"] == "COMPLETED":
            return dict(previous["report"])
        self.output_directory.mkdir(parents=True, exist_ok=False)
        self.store.save_campaign(campaign_id, "RUNNING", {"baseline_id": baseline.id, "results": []})
        baseline_summary = self.supervisor.run(
            baseline, kind="baseline", scenario=scenario, vblanks=min(vblanks, self.budget.max_vblanks_per_experiment)
        )
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        stop_reason = "max_experiments"
        for index in range(min(self.budget.max_experiments, self.budget.max_codex_calls)):
            if time.monotonic() - started >= self.budget.max_seconds:
                stop_reason = "max_seconds"
                break
            proposal = self.client.propose(
                ResearchContext(
                    unresolved_question="identify one evidence-backed fake render cadence experiment",
                    confirmed_facts=("fake baseline completed",),
                    trace_statistics=baseline_summary.to_dict(),
                    prior_results=tuple(results),
                    remaining_experiments=self.budget.max_experiments - index,
                )
            )
            fingerprint = json.dumps(proposal.to_dict()["changes"], sort_keys=True)
            if fingerprint in seen:
                stop_reason = "duplicate_candidate"
                break
            seen.add(fingerprint)
            candidate_summary = self.supervisor.run(
                proposal, kind="candidate", scenario=scenario, vblanks=min(vblanks, self.budget.max_vblanks_per_experiment)
            )
            comparison = compare_summaries(baseline.id, proposal.id, baseline_summary, candidate_summary)
            results.append({"proposal_id": proposal.id, "comparison": comparison.to_dict()})
            stop_reason = "fake_client_exhausted"
            break
        report = {
            "created_at": datetime.now(UTC).isoformat(),
            "budget": asdict(self.budget),
            "baseline_id": baseline.id,
            "results": results,
            "stop_reason": stop_reason,
            "elapsed_seconds": time.monotonic() - started,
        }
        (self.output_directory / "campaign.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.store.save_campaign(campaign_id, "COMPLETED", report)
        return report
