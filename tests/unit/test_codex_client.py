from pathlib import Path

import pytest

from r4_autolab.codex_client import CodexExecClient, FakeCodexClient, ResearchContext
from r4_autolab.models import ExperimentProposal, TargetVersion


def context() -> ResearchContext:
    return ResearchContext("question", ("fact",), {}, (), 1)


def test_fake_codex_returns_only_queued_proposals() -> None:
    proposal = ExperimentProposal("p", "hypothesis", TargetVersion("FAKE", "0" * 64))
    client = FakeCodexClient([proposal])
    assert client.propose(context()) == proposal
    with pytest.raises(RuntimeError, match="no remaining"):
        client.propose(context())


def test_real_codex_is_disabled_and_uses_schema_read_only_args(tmp_path: Path) -> None:
    client = CodexExecClient(Path("codex"), tmp_path / "schema.json", tmp_path, enabled=False)
    arguments = client.build_args(tmp_path / "out.json", "prompt")
    assert arguments[:3] == ["codex", "exec", "--ephemeral"]
    assert arguments[arguments.index("--sandbox") + 1] == "read-only"
    assert "--output-schema" in arguments
    with pytest.raises(RuntimeError, match="explicit"):
        client.propose(context())
