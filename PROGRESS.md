# R4 AutoLab progress

この文書は `Agents.md` のPhase単位で、確認済み事実、実装、検証、ブロッカー、Gitコミットを記録する。推測を完了扱いにしない。

## Overall status

| Phase | Status | Evidence |
|---|---|---|
| Phase 0: Repository audit | COMPLETE | Repository plan, architecture, immutable asset rules |
| Phase 1: Safe scaffold | COMPLETE | CLI, configuration, SQLite, fake emulator, tests |
| Phase 2: Reproducible supervisor | COMPLETE (MVP scope) | State transitions, artifacts, restore paths, comparisons |
| Phase 3A: PCSX-Redux minimum capabilities | COMPLETE | Real arm64 bridge capability report; read-only checks passed |
| Phase 3B: PCSX-Redux remaining bridge | IN PROGRESS | Save-state/breakpoint/write-disconnect/real baseline hardening |
| Phase 4: Static analysis bridge | PENDING | Ghidra is not installed; fake adapter will remain asset-free |
| Phase 5: Automated evaluation | PENDING | Basic evaluator exists; full timing/physics/render/visual profiles remain |
| Phase 6: Codex research loop | PENDING | Campaign is dry-run validation only |
| Phase 7: First R4 investigation | PENDING | Owned disc exists; deterministic race state/input not yet configured |

## Section 1 — Baseline audit (Phase 0 through Phase 3A)

Date: 2026-07-17 JST

### Confirmed

- Branch `feat/pcsx-redux-bridge` matches GitHub before continuation.
- 32 tests pass and mypy reports no issues in 18 source files.
- `doctor` detects Python 3.14.6, Git, Codex CLI, Java, and arm64 PCSX-Redux build `4ad775e47d47cc9023aa45a2f439289c5897801a`.
- Real PCSX-Redux capability checks pass for launch, authenticated localhost IPC, pause/resume, VBlank events, counters, registers, read-only memory, raw screenshot, shutdown, and process cleanup.
- Scratch write remains skipped; no R4 candidate address was written.
- BIN/CUE, run artifacts, local config, save states, and virtual environments remain ignored by Git.

### Boundaries retained

- No 60 fps patch, NOP, Ghidra analysis, or Codex campaign has been run.
- General real-mode experiments remain fail-closed.
- The latest capability artifacts remain local under `runs/capabilities/` and are not committed.

### GitHub

- Initial MVP: `33059d4`
- Phase 3A bridge: `d3f2af0`
- Phase 3A formatting follow-up: `96a2281`

