from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Protocol

from .models import ExperimentProposal


@dataclass(frozen=True)
class ResearchContext:
    unresolved_question: str
    confirmed_facts: tuple[str, ...]
    trace_statistics: dict[str, Any]
    prior_results: tuple[dict[str, Any], ...]
    remaining_experiments: int

    def to_prompt(self) -> str:
        return json.dumps(
            {
                "unresolved_question": self.unresolved_question,
                "confirmed_facts": self.confirmed_facts,
                "trace_statistics": self.trace_statistics,
                "prior_results": self.prior_results,
                "remaining_experiments": self.remaining_experiments,
                "instruction": "Return exactly one schema-valid experiment proposal. Do not write memory or run commands.",
            },
            indent=2,
            sort_keys=True,
        )


class CodexClient(Protocol):
    def propose(self, context: ResearchContext) -> ExperimentProposal: ...


class FakeCodexClient:
    def __init__(self, proposals: list[ExperimentProposal]) -> None:
        self.proposals = list(proposals)
        self.calls = 0

    def propose(self, context: ResearchContext) -> ExperimentProposal:
        del context
        self.calls += 1
        if not self.proposals:
            raise RuntimeError("fake Codex has no remaining proposals")
        return self.proposals.pop(0)


class CodexExecClient:
    """Explicitly gated non-interactive Codex adapter with schema-constrained output."""

    def __init__(
        self,
        executable: Path,
        schema_path: Path,
        output_directory: Path,
        *,
        enabled: bool = False,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.executable = executable
        self.schema_path = schema_path
        self.output_directory = output_directory
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.calls = 0

    def build_args(self, output_path: Path, prompt: str) -> list[str]:
        return [
            str(self.executable),
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--output-schema",
            str(self.schema_path),
            "--output-last-message",
            str(output_path),
            prompt,
        ]

    def propose(self, context: ResearchContext) -> ExperimentProposal:
        if not self.enabled:
            raise RuntimeError("real Codex execution requires explicit enabled=True configuration")
        self.calls += 1
        self.output_directory.mkdir(parents=True, exist_ok=True)
        output = self.output_directory / f"proposal-{self.calls:04d}.json"
        subprocess.run(
            self.build_args(output, context.to_prompt()),
            cwd=self.output_directory,
            shell=False,
            timeout=self.timeout_seconds,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        value = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Codex proposal output must be a JSON object")
        return ExperimentProposal.from_dict(value)
