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
| Phase 5: Automated evaluation | COMPLETE FOR CONFIGURED TELEMETRY | Cadence, trajectories, thresholds, stability, raw visual checks |
| Phase 6: Codex research loop | COMPLETE IN FAKE/DRY MODE | Schema-gated adapter, budgets, SQLite resume, fake campaign |
| Phase 7: First R4 investigation | COMPLETE FOR BOOT / BLOCKED FOR RACE | Target identity and bounded Read/Write boot trace complete; race state/input absent |
| Race-state capture | IMPLEMENTED / REAL CAPTURE PENDING | One-Enter raw capture, source hashes, three-process validation, ignored config registration |

Overall implementation status: **CURRENT-ENVIRONMENT COMPLETE; EXTERNAL RACE EVIDENCE BLOCKED**.

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

## Section 4 — Phase 5 automated evaluation

Date: 2026-07-17 JST

### Implemented

- Generic field cadence analysis with update frequency and duplicate ratio.
- VBlank-aligned maximum trajectory divergence for position, speed, and RPM.
- TOML threshold evaluation for timer ratio, physics, rendering uniqueness, duplicates, and stability.
- Deterministic 16/24-bpp raw screenshot checks for dimensions, byte integrity, black/extreme ratios, and SHA-256.
- `compare` now emits evidence checks; `visual-check` provides a standalone oracle.

### Verification

- Fake baseline measured ~30.25 GPU-state changes/s; render-only candidate measured 60.0/s.
- Candidate evaluation passed with timer ratio 1.0 and zero configured physics divergence.
- Real capability screenshot passed 640×478×16-bpp byte-size validation.
- `pytest`: 38 passed.
- `mypy src`: success for 24 source files.

### Remaining evidence dependencies

- AI, lap, gear, steering, collision, drift, and replay checks are implemented only when those fields are supplied by a future real trace configuration; no success claim is made without them.

## Section 5 — Phase 6 constrained Codex research loop

Date: 2026-07-17 JST

### Implemented

- Exchangeable `CodexClient`, deterministic Fake client, and explicitly disabled real `codex exec` client.
- Real adapter argument construction uses ephemeral, read-only, JSON-Schema-constrained output and final-message file capture.
- Campaign budgets, one-proposal context compression, change deduplication, SQLite campaign status, JSON report, and completed-run resume.
- `campaign --execute` requires `--fake-codex`; no real nested Codex invocation is reachable by default.

### Verification

- Fake campaign completed baseline and one render-only candidate with game-speed ratio 1.0 and zero position/speed/RPM delta.
- Campaign integration exposed and fixed a Fake Emulator VBlank-reset reproducibility bug.
- `pytest`: 41 passed.
- `mypy src`: success for 26 source files.

### Real Codex boundary

- No real Codex subprocess or API call was made.
- Real enablement requires a separate trusted deployment setting and operator-approved non-zero cost budget; default example cost remains 0.0.
- The adapter follows the current official non-interactive Codex schema-output and least-privilege guidance documented in `docs/CODEX_LOOP.md`.

## Section 6 — Phase 7 first R4 investigation

Date: 2026-07-17 JST

### Confirmed target

- Read-only MODE2/2352 ISO9660 extraction identified `SLPS_018.00;1` / `SLPS-01800`.
- Executable SHA-256: `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775`.
- Load address `0x80010000`; initial PC `0x8007D4B4`; payload 638,976 bytes.

### Dynamic boot observation

- 600 VBlank, eight configured watches, bounded Read/Write breakpoints, no patches or memory writes.
- 46 breakpoint events collected with PC, RA, accessed address, width, and cause.
- Camera candidate `0x801FFF58` had four sampled changes and multiple runtime Read/Write PCs.
- Frame/vehicle/speed/RPM candidates remained zero and showed only initialization writes; their race semantics remain unverified.
- Full evidence and confidence labels are in `docs/FIRST_R4_OBSERVATION.md`.

### Bugs found and fixed

- Serial normalization no longer drops the `.00` suffix.
- Lua breakpoint IDs now use a monotonic counter rather than the length of a string-keyed table.
- Read breakpoints have a per-breakpoint hit budget to prevent event floods.

### Test status and blockers

- `pytest`: 42 passed.
- `mypy src`: success for 28 source files.
- Race-level continuation is blocked by the absence of a deterministic private race `.rawstate`, input script, and installed Ghidra. Boot results are not promoted to race conclusions.

## Section 7 — Final acceptance audit

Date: 2026-07-17 JST

- Full asset-free suite: 42 passed.
- Strict type checking: 28 source files, no issues.
- Real extended PCSX capability: PASS except intentionally unrequested scratch write.
- Fake static export and Fake Codex campaign: PASS.
- First owned-disc identity and bounded boot Read/Write observation: complete.
- Final requirement matrix and exact resume conditions: `docs/FINAL_AUDIT.md`.
- No 60 fps patch or success claim was produced.

## Section 8 — Interactive race-state capture implementation

Date: 2026-07-17 JST

### Implemented

- Added `capture-manual-state` with automatic verified CUE/BIN and BIOS/OpenBIOS discovery.
- Normal interactive PCSX launch excludes `-testmode` while retaining the authenticated Lua bridge, interpreter, and debugger.
- The manual prompt is shown only after handshake and a sampled PC enters the verified R4 payload.
- Enter triggers pause-first register/counter/watch capture, raw screenshot, raw-protobuf state creation, source/state hashing, and same-process reload.
- Default cleanup launches three independent state-validation processes and records initial plus 60-VBlank evidence.
- Local real-mode paths and the state are written only to ignored `config/project.toml`; generated artifacts remain under ignored `states/` and `runs/`.

### Verification before real capture

- `pytest`: 45 passed.
- `mypy src`: success for 29 source files.
- `git check-ignore`: state, raw screenshot, validation report, local config, CUE, and BIN all matched explicit ignore rules.
- Real extended PCSX capability smoke remains PASS, including raw-state roundtrip and breakpoint lifecycle.

### Next transition

The implementation is ready to launch. The only pending human action is navigating R4 to a stable straight during a race and pressing Enter once; validation and subsequent read-only analysis continue automatically.
