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
| Phase 4: Static analysis bridge | COMPLETE WITH REAL SMOKE | Official Ghidra 12.1.2, verified PS-X payload mapping, selected dynamic-PC export |
| Phase 5: Automated evaluation | COMPLETE FOR CONFIGURED TELEMETRY | Cadence, trajectories, thresholds, stability, raw visual checks |
| Phase 6: Codex research loop | COMPLETE IN FAKE/DRY MODE | Schema-gated adapter, budgets, SQLite resume, fake campaign |
| Phase 7: First R4 investigation | COMPLETE FOR FIRST RACE TIMING MODEL | Deterministic race, overlay mapping, real vehicle fields, 30 Hz subsystem and display cadence |
| Race-state capture | COMPLETE | One-Enter raw capture and three-process deterministic reload PASS |
| Deterministic input | COMPLETE | Official Lua Pad override; five scenarios × three attempts PASS |
| Deterministic race trace | COMPLETE FOR PUBLISHED CANDIDATES | 600 VBlanks; bounded ordered Read/Write phases; public vehicle addresses disproven |
| Real static correlation | COMPLETE FOR BASE + RACE OVERLAY | Stack false-positive rejection plus active overlay and object/function mapping |
| Race timing model | COMPLETE FOR ONE STATE | Physics/AI dispatcher, camera, timer, main loop, and raw displayed image all 30 Hz |

Overall implementation status: **FIRST RACE TIMING MODEL COMPLETE; SAFE PATCH EVIDENCE NOT YET ESTABLISHED**.

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

### Transition result

The one-time manual navigation and Enter capture completed successfully. Section 9 records the resulting state and reproducibility evidence.

## Section 9 — Real race-state capture and validation

Date: 2026-07-17 JST

### Captured evidence

- Ignored state: `states/manual-race-20260716T171240718201Z/race_straight.rawstate`.
- State SHA-256: `a80f4a2c1dead74c41e309fe0762b397e635e390ba46ce8251f016b3c595c1e7`.
- Size: 19,063,530 bytes; source CUE/BIN hashes remained unchanged.
- Raw screenshot is valid 320×240×16-bpp and visibly shows an active race straight at approximately 95 km/h.
- Local `config/project.toml` now selects real mode, the verified disc/state, scenario `race-straight`, and 120 VBlanks. It remains ignored.

### Three-process reproducibility

- Three fresh PCSX-Redux processes loaded the raw state successfully and shut down without residue.
- Initial candidate bytes, 60-VBlank candidate trajectories, initial screenshot hash, and final screenshot hash matched across all attempts.
- Pause sampling consistently caught the PS1 general exception vector `PC=0x80000080` with target return `RA=0x8008AFCC`; the validator now recognizes this standard interrupt context instead of requiring PC alone to be inside the payload.
- Final validation classification: **PASS**.
- Public-address candidates except `0x801FFF58` remained zero despite the visible race, so their Japanese-version semantics are not assumed and must be rediscovered from trace evidence.

### Verification

- `pytest`: 46 passed.
- `mypy src`: success for 29 source files.
- No R4 memory write or patch was performed.

## Section 10 — Deterministic input replay

Date: 2026-07-17 JST

### Implementation

- Added official PCSX-Redux Pad override operations for controller 1, with a strict 16-button allowlist and contradictory-direction rejection.
- Added VBlank-bounded replay, per-scenario canonical SHA-256, 60-VBlank candidate/screenshot sampling, and fresh-process attempts.
- Input is released after each run, on Python exceptions, before bridge shutdown, and on the Lua `Quitting` event.
- Added the required neutral, acceleration, left, right, and acceleration-plus-steering scenarios.

### Real verification

- Five scenarios × three attempts: **PASS**.
- Every scenario had identical complete candidate/screenshot trajectories across all three attempts.
- Every scenario changed the visible screen and acknowledged final input release.
- Left, right, and acceleration-plus-left produced distinct final screen hashes; the camera candidate moved in opposite directions for left/right.
- No PCSX-Redux child remained and no game memory write or patch occurred.

### Input identities

- `neutral-120`: `72917ed36ba5cc81c29f2b5e82645f4cd33fd2229b68305be0e62e320c3ee6d8`
- `accelerate-straight-600`: `53632bf889065e6aea47f6ab054ba1910ae7f5df3c59579744e414ebcf02429a`
- `steer-left-300`: `cc80765cf7e03e2705273c4fbd29a0568f1f9e57fd78a489f7312b5c3879c387`
- `steer-right-300`: `cc549a7914be79870911596997eb5b140e78fe52f6b1a154abf1ce70d6ebee06`
- `accelerate-and-steer-600`: `d4654a9d48923549cac753a435e6f1793face25d122c91f1a85f793245fb1040`

## Section 11 — Bounded deterministic race trace

Date: 2026-07-17 JST

### Execution

- Collected exactly 600 race VBlanks with deterministic acceleration and all eight configured watches.
- Ran ordered Write phases for frame, XYZ, speed, RPM, heading, and camera candidates, then Read phases for XYZ and camera.
- Every breakpoint was limited to 32 hits and every phase reloaded the verified state before 120 VBlanks.
- Events include VBlank, CPU cycle, PC/RA/SP/GPR, access/cause, scenario, state hash, and input hash.

### Evidence

- Frame/XYZ/heading/speed/RPM published candidates: constant zero, zero bounded accesses.
- `0x801FFF58`: 299 changes over 600 samples, approximately 29.985 Hz, with capped 32 Write and 32 Read events.
- `0x801FFF58` lies 0x38 bytes below captured SP and has many unrelated source PCs; its public camera label is rejected pending stronger mapping.
- PASS: all phases completed, cleanup succeeded, 600 telemetry and 64 bounded breakpoint events retained locally.
- No candidate address write, RAM patch, large dump, or unbounded exploration occurred.

## Section 12 — Official Ghidra installation and real export

Date: 2026-07-17 JST

### Environment

- Official Ghidra 12.1.2 asset from NSA GitHub Releases, installed without administrator privileges under ignored `private/tools/ghidra/`.
- ZIP SHA-256 matched official digest `b62e81a0390618466c019c60d8c2f796ced2509c4c1aea4a37644a77272cf99d`.
- OpenJDK 21.0.11; doctor now detects the locally configured `analyzeHeadless`.

### Verified import and export

- Raw BinaryLoader mapped exactly the 638,976-byte payload from file offset `0x800` to `0x80010000–0x800ABFFF` as MIPS little-endian.
- Verified entry point `0x8007D4B4` was established before analysis.
- Real export: 1,456 functions, 16,979 basic blocks, 3,034 call edges, 251 strings, and three selected decompilations.
- Export includes function ranges/file offsets, xrefs, surrounding MIPS with delay slots, computed jumps, memory blocks, and pseudocode.

### Dynamic/static conclusion

- `0x80050194` / `0x800501B0`: save/restore `ra` at `0x10(sp)` in `FUN_80050168`.
- `0x80084C28` / `0x80084D2C`: save/restore `s4` at `0x20(sp)` in `FUN_80084c10`.
- These instructions explain the apparent `0x801FFF58` camera events as stack reuse. The public camera hypothesis is rejected for this build.
- Ghidra's function signatures and pseudocode remain hypotheses and are not treated as ground truth.

## Section 13 — Race overlay, real state fields, and timing model

Date: 2026-07-17 JST

### Overlay and object discovery

- Runtime fingerprinting located two owned-disc overlay regions separated by `0x46000`; private bounded extracts remain ignored.
- Ghidra mapped the active overlay at `0x801146F0`, with race entry `0x80114780`, 504 function candidates, and 494 call edges.
- The overlay identifies `0x800FFA00 -> 0x800ABCE0` as the player object. Targeted reads confirmed moving position, orientation, speed, rank, lap, and progress fields without scanning RAM.

### Dynamic timing evidence

- Main-loop landmarks and race overlay entry: exactly 300 hits / 600 VBlanks.
- Vehicle/AI dispatcher `0x80038338`, camera `0x80034178`, lap/timer `0x8003C838`, and frame post-processing `0x8004AA7C`: exactly one hit on each active 30 Hz frame.
- Player X/Z: 299 changes / 600 at 30.013 Hz; speed-related field changed 267 times.
- 121 consecutive raw screenshots produced 60 transitions; after the initial sample, every hash repeats for exactly two VBlanks. Displayed-image cadence is 29.97 Hz with 50% duplicate transitions.
- No memory write, patch, NOP, disc/BIOS modification, or unbounded dump occurred. No PCSX process remained.
- A host-level nonblocking lock now rejects a second concurrent AutoLab PCSX launch, preventing accidental doubled audio/processes.

### Gate decision

The race update, physics/AI, camera, timer, HUD/render work, and displayed image are currently coupled at 30 Hz. Doubling the integrated loop is unsafe and no isolated render-only candidate is yet supported. Patch generation therefore remains disabled. Full evidence is in `docs/R4_TIMING_MODEL.md`.
