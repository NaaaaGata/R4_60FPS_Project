# R4 AutoLab progress

この文書は `Agents.md` のPhase単位で、確認済み事実、実装、検証、ブロッカー、Gitコミットを記録する。推測を完了扱いにしない。

## Overall status

| Phase | Status | Evidence |
|---|---|---|
| Phase 0: Repository audit | COMPLETE | Repository plan, architecture, immutable asset rules |
| Phase 1: Safe scaffold | COMPLETE | CLI, configuration, SQLite, fake emulator, tests |
| Phase 2: Reproducible supervisor | COMPLETE (MVP scope) | State transitions, artifacts, restore paths, comparisons |
| Phase 3A: PCSX-Redux minimum capabilities | COMPLETE | Real arm64 bridge capability report; read-only checks passed |
| Phase 3B: PCSX-Redux remaining bridge | COMPLETE | Extended real smoke: breakpoint lifecycle and raw-state roundtrip passed |
| Phase 4: Static analysis bridge | COMPLETE WITH REAL-SMOKE BLOCKER | Headless runner/cache/export script/fake tests complete; Ghidra absent |
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

## Section 2 — Phase 3B PCSX-Redux bridge completion

Date: 2026-07-17 JST

### Implemented

- Emulator adapters now expose an explicit connect boundary; the Supervisor connects before state or memory operations.
- PCSX `run_vblanks` waits for a bounded `vblank_target_reached` event instead of returning before collection.
- Raw protobuf save-state creation and loading use an explicit `.rawstate` format; ambiguous and UI gzip formats remain rejected.
- Capability runner supports explicit extended read-only smoke flags for non-firing breakpoint create/remove and save-state roundtrip.
- General real-mode baseline construction is connected but still requires explicit private `disc_path`; no path is guessed.
- Unsupported real GPU-log export is recorded as an explicit artifact note instead of a fabricated log.

### Real evidence

- Extended capability report: `runs/capabilities/pcsx-20260716T163234351518Z/capabilities.json` (local, ignored).
- PASS: launch, IPC, handshake, pause/resume, 10 VBlanks, counters, registers, safe read, screenshot, breakpoint create/remove, 19,026,416-byte raw-state create/load, shutdown, process cleanup.
- SKIP: scratch write, because no explicit `--allow-scratch-write` and operator-confirmed address were supplied.
- An earlier raw-state check failed because PCSX File writes are asynchronous; deadline-bounded polling fixed the race and the failed report remains local.

### Test status

- `pytest`: 33 passed.
- `mypy src`: success for 18 source files.

## Section 3 — Phase 4 static analysis bridge

Date: 2026-07-17 JST

### Implemented

- Official `analyzeHeadless` discovery, argument-array builder, timeout, isolated temporary project, logs, and content-addressed cache.
- `ghidra-export` CLI with real and explicit `--fake` modes; real mode fails closed when Ghidra is absent.
- Headless `R4Export.java` for functions, basic blocks, calls, requested-address xrefs/disassembly, strings, and overlay blocks.
- JSON export validation and deterministic fake integration.

### Verification

- Fake export command completed and cache artifacts were written under ignored `runs/static-cache/`.
- `pytest`: 35 passed.
- `mypy src`: success for 21 source files.

### External blocker

- `analyzeHeadless` is not installed or configured on this Mac. No Ghidra binary was downloaded.
- The Java export script therefore remains uncompiled against a concrete Ghidra release.
- Real continuation requires an official local Ghidra/JDK installation and an extracted, hashed PS-X EXE in an ignored path. Detailed steps are in `docs/STATIC_ANALYSIS.md`.
