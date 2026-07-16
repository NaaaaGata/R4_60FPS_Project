# Codex research loop

Phase 6 separates proposal generation from emulator control. `CodexClient` receives compressed confirmed facts, trace statistics, prior results, and remaining budget; it returns one `experiment_proposal.schema.json` object. The Supervisor remains the only component allowed to validate and apply a proposal.

`CodexExecClient` is disabled by default. Explicit `campaign --execute --real-codex` uses official non-interactive controls: `codex exec --ephemeral --ignore-user-config --sandbox read-only --config web_search="disabled" --output-schema ... --output-last-message ...`. On macOS, the executable must also pass strict `codesign` verification. The [Codex non-interactive manual](https://learn.chatgpt.com/docs/non-interactive-mode) documents schema-constrained output and least-privilege sandboxes.

Asset-free execution is available with:

```bash
r4-autolab campaign --config config/budgets.example.toml --execute --fake-codex
```

The runner validates all mandatory finite budgets, records baseline/candidate experiments in SQLite, deduplicates identical changes, stores campaign status/report in SQLite, writes an ignored JSON report, and returns an already completed campaign record on resume. Fake execution performs one deterministic candidate and stops; it does not recursively call Codex.

Real proposal-only execution is available with a separate, non-zero finite budget:

```bash
r4-autolab campaign --config config/budgets.real.example.toml --execute --real-codex
```

The current evidence catalog is empty. Consequently, a no-change proposal stops as `NO_SAFE_CHANGE`, while any proposed write is rejected before PCSX-Redux launch. This path cannot run an emulator candidate; candidate execution still requires a separately reviewed evidence catalog and Supervisor handoff. API keys are not committed or inherited by unrelated repository processes.

The first real run made one Codex call and returned no change. Two preceding strict-schema compatibility failures were recorded as FAILED with zero emulator experiments; they led to requiring every declared property and disallowing arbitrary object fields in the output schema.
