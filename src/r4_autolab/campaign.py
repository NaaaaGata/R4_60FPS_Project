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
from .models import TargetVersion
from .safety import PatchValidator, SafetyViolation
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


class ProposalCampaignRunner:
    """Run schema-constrained research proposals without granting emulator control."""

    def __init__(
        self,
        store: ExperimentStore,
        client: CodexClient,
        budget: CampaignBudget,
        output_directory: Path,
        target: TargetVersion,
        confirmed_facts: tuple[str, ...],
        allowed_change_fingerprints: frozenset[str] = frozenset(),
    ) -> None:
        self.store = store
        self.client = client
        self.budget = budget
        self.output_directory = output_directory
        self.target = target
        self.confirmed_facts = confirmed_facts
        self.allowed_change_fingerprints = allowed_change_fingerprints

    def run(self) -> dict[str, Any]:
        if self.budget.max_cost <= 0:
            raise ValueError("real Codex campaign requires a non-zero finite max_cost")
        positive_limits = {
            "max_experiments": self.budget.max_experiments,
            "max_seconds": self.budget.max_seconds,
            "max_codex_calls": self.budget.max_codex_calls,
            "max_consecutive_crashes": self.budget.max_consecutive_crashes,
            "max_consecutive_no_progress": self.budget.max_consecutive_no_progress,
            "max_storage_bytes": self.budget.max_storage_bytes,
            "max_vblanks_per_experiment": self.budget.max_vblanks_per_experiment,
            "max_changes_per_experiment": self.budget.max_changes_per_experiment,
            "max_retries_per_candidate": self.budget.max_retries_per_candidate,
        }
        invalid = sorted(name for name, value in positive_limits.items() if value <= 0)
        if invalid:
            raise ValueError("real Codex campaign limits must be positive: " + ", ".join(invalid))
        if self.budget.max_changes_per_experiment != 1:
            raise ValueError("real Codex campaign requires exactly one maximum change per experiment")
        started = time.monotonic()
        campaign_id = self.output_directory.name
        self.output_directory.mkdir(parents=True, exist_ok=False)
        report: dict[str, Any] = {
            "created_at": datetime.now(UTC).isoformat(),
            "mode": "real-codex-proposal-only",
            "budget": asdict(self.budget),
            "target": asdict(self.target),
            "proposals": [],
            "emulator_experiments": 0,
            "stop_reason": "max_codex_calls",
        }
        self.store.save_campaign(campaign_id, "RUNNING", report)
        validator = PatchValidator(max_changes=self.budget.max_changes_per_experiment)
        status = "COMPLETED"
        try:
            for index in range(min(self.budget.max_codex_calls, self.budget.max_experiments)):
                if time.monotonic() - started >= self.budget.max_seconds:
                    report["stop_reason"] = "max_seconds"
                    break
                proposal = self.client.propose(
                    ResearchContext(
                        unresolved_question=(
                            "Does the confirmed integrated 30 Hz loop support one exact render-only RAM change? "
                            "Return changes=[] when the evidence is insufficient."
                        ),
                        confirmed_facts=self.confirmed_facts,
                        trace_statistics={"allowed_evidence_backed_changes": len(self.allowed_change_fingerprints)},
                        prior_results=tuple(report["proposals"]),
                        remaining_experiments=self.budget.max_experiments - index,
                    )
                )
                entry: dict[str, Any] = {"proposal": proposal.to_dict()}
                try:
                    validator.validate_proposal(proposal, self.target)
                    if not proposal.changes:
                        entry["decision"] = "NO_SAFE_CHANGE"
                        report["stop_reason"] = "model_reported_insufficient_evidence"
                        report["proposals"].append(entry)
                        break
                    fingerprint = json.dumps(proposal.to_dict()["changes"], sort_keys=True)
                    if fingerprint not in self.allowed_change_fingerprints:
                        raise SafetyViolation("proposal change is absent from the reviewed evidence catalog")
                    entry["decision"] = "CANDIDATE_REQUIRES_SEPARATE_EXECUTION_REVIEW"
                    report["stop_reason"] = "candidate_requires_separate_execution_review"
                    report["proposals"].append(entry)
                    break
                except SafetyViolation as error:
                    entry["decision"] = "REJECTED"
                    entry["reason"] = str(error)
                    report["proposals"].append(entry)
                    report["stop_reason"] = "evidence_gate_rejected"
                    break
        except Exception as error:
            status = "FAILED"
            report["stop_reason"] = "codex_client_error"
            report["error"] = f"{type(error).__name__}: {error}"
        report["elapsed_seconds"] = time.monotonic() - started
        report["codex_calls"] = int(getattr(self.client, "calls", len(report["proposals"])))
        (self.output_directory / "campaign.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.store.save_campaign(campaign_id, status, report)
        return report
