# Codex research loop

Phase 6 separates proposal generation from emulator control. `CodexClient` receives compressed confirmed facts, trace statistics, prior results, and remaining budget; it returns one `experiment_proposal.schema.json` object. The Supervisor remains the only component allowed to validate and apply a proposal.

`CodexExecClient` is disabled by default. When explicitly enabled by deployment, it uses official non-interactive Codex controls: `codex exec --ephemeral --sandbox read-only --output-schema ... --output-last-message ...`. The [Codex non-interactive manual](https://learn.chatgpt.com/docs/non-interactive-mode) documents schema-constrained final output and recommends least-privilege sandboxes. This repository never enables real nested Codex from the default campaign command.

Asset-free execution is available with:

```bash
r4-autolab campaign --config config/budgets.example.toml --execute --fake-codex
```

The runner validates all mandatory finite budgets, records baseline/candidate experiments in SQLite, deduplicates identical changes, stores campaign status/report in SQLite, writes an ignored JSON report, and returns an already completed campaign record on resume. Fake execution performs one deterministic candidate and stops; it does not recursively call Codex.

Real Codex continuation requires a separate explicit deployment setting, a trusted repository, reviewed schema/context, and a non-zero operator-approved cost budget. API keys must not be committed or inherited by unrelated repository processes.
