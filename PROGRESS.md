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
| Phase 6: Codex research loop | COMPLETE WITH REAL PROPOSAL SMOKE | Signed CLI, strict schema, one-call finite budget, zero-emulator evidence gate |
| Phase 7: First R4 investigation | COMPLETE FOR FIRST RACE TIMING MODEL | Deterministic race, overlay mapping, real vehicle fields, 30 Hz subsystem and display cadence |
| Race-state capture | COMPLETE | One-Enter raw capture and three-process deterministic reload PASS |
| Deterministic input | COMPLETE | Official Lua Pad override; five scenarios × three attempts PASS |
| Deterministic race trace | COMPLETE FOR PUBLISHED CANDIDATES | 600 VBlanks; bounded ordered Read/Write phases; public vehicle addresses disproven |
| Real static correlation | COMPLETE FOR BASE + RACE OVERLAY | Stack false-positive rejection plus active overlay and object/function mapping |
| Race timing model | COMPLETE FOR ONE STATE | Physics/AI dispatcher, camera, timer, main loop, and raw displayed image all 30 Hz |
| Scratch restoration gate | COMPLETE FOR ONE NON-CODE WORD | Five scenarios / 1,920 VBlanks unaccessed; paused write/read/restore PASS |
| 60 fps candidate gate | COMPLETE: NO SAFE CHANGE | Integrated 30 Hz loop; zero R4 patches; real Codex returned no change |

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

Historical snapshot: the blocker below was true at Section 3 and was resolved in Section 12.

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

Historical snapshot: real execution was disabled at this stage and was enabled safely in Section 15.

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

Historical snapshot: these boot-only blockers were resolved by Sections 9–13.

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

## Section 14 — Scratchpad read-only audit and restoration proof

Date: 2026-07-17 JST

- Added `audit-scratch`, restricted to one aligned word inside the PS1 scratchpad and using bounded Read/Write breakpoints.
- `0x1F8003FC` remained `00000000` with zero accesses across all five deterministic scenarios and 1,920 total VBlanks; the test was repeated after the memory backend correction.
- The first explicit write test failed read-back using `getMemoryAsFile().writeAt`, then ran restoration, shutdown, and cleanup. No alternate game address was tried.
- Official `PCSX.getScratchPtr()` is now used only for fully range-checked scratchpad requests. All other memory retains the safer File API.
- The corrected paused test verified `00000000 -> a5a5a5a5 -> 00000000`; scratch write, restoration, shutdown, and child cleanup all PASS.
- No R4 candidate address, game code, disc image, BIOS, or save-state content was modified. This proves bridge restoration only, not a patch candidate.

## Section 15 — Evidence-gated candidate and real Codex campaign

Date: 2026-07-17 JST

- Strict Structured Outputs schema now requires every declared property, rejects undeclared fields, and gives predicted effects a fixed nullable shape.
- Real Codex discovery records executable identity and requires strict macOS code-signature verification before invocation.
- Added `config/budgets.real.example.toml`: one call, one proposal, 300 seconds, one change maximum, and non-zero finite accounting budget.
- Real invocation is ephemeral, read-only, ignores user configuration, disables web search, and writes only ignored campaign artifacts.
- Supervisor-side evidence catalog contains zero reviewed changes. Any write proposal is rejected before emulator launch; no-change stops cleanly.
- One real signed Codex 0.144.5 call completed in 7.74 seconds and returned `changes=[]`, classified `NO_SAFE_CHANGE`; emulator experiments and R4 writes remained zero.
- A final bounded GPU-function trace confirmed submit calls only on 60 of 120 VBlanks: `0x8009331C` and `0x80093150` once per active frame, `0x800930E0` twice per active frame.
- Two prior strict-schema errors are retained as FAILED SQLite campaigns with exact logs and zero emulator experiments.
- Phase L/M patch execution is SKIP by evidence gate, not incomplete automation. Detailed accounting is in `docs/R4_CANDIDATE_RESULTS.md`.

### macOS blocked legacy CLI

An attempted version check touched stale Homebrew Cask Codex 0.125.0. macOS correctly blocked it because its signature was invalid and moved it to Trash. No bypass was used. The active VS Code extension ships separate Codex 0.144.5; its on-disk signature and designated requirement passed before the real campaign. The blocked legacy binary was never used for a campaign.

## Section 16 — Final acceptance and delivery

Date: 2026-07-17 JST

- `pytest`: 67 passed.
- `mypy src`: success for 36 source files.
- `doctor`: Python, Git, current Codex, PCSX-Redux, Ghidra, and Java detected.
- Final extended PCSX smoke: launch, IPC, handshake, pause/resume, VBlank, counters, registers, memory read, screenshot, breakpoint lifecycle, raw-state roundtrip, shutdown, and process cleanup all PASS.
- Real campaign budget dry-run PASS; real one-call proposal campaign completed `NO_SAFE_CHANGE` with zero emulator experiments.
- Tracked-file audit found no state, run, private asset, BIN, CUE, extracted executable, or raw capture.
- `git diff --check`: clean. `.metals/` and `.vscode/` remain unrelated untracked IDE directories and are excluded.
- Final matrix, exact unresolved items, and reproduction commands are in `docs/FINAL_AUDIT.md`.

## Section 17 — Render-boundary branch and loop parity

Date: 2026-07-17 JST

- Created `feat/render-boundary-analysis` from `feat/race-state-analysis`; private assets and unrelated `.metals/` / `.vscode/` remain untracked and untouched.
- Revalidated 67 tests, mypy, doctor, extended read-only PCSX capabilities, exact state SHA-256, and all five deterministic inputs before analysis.
- Extended the bounded Ghidra exporter with conditional-branch target, fall-through, predecessor, and delay-slot metadata.
- Added a tested MIPS branch decoder and executable-identity-locked branch inventory.
- Added a second read-only enforcement layer in Python and Lua; `write_memory` is rejected before IPC when enabled.
- `trace-loop-parity` measured 600 VBlanks with 12 bounded Exec breakpoints and 16 fixed reads: 300 active and 300 duplicate intervals in exact alternation.
- Main/race/vehicle/camera/timer/post and GPU submissions occur only on active intervals; every fixed watch and screenshot hash is unchanged on duplicates.
- Exact wait branch: `0x8001EC54 bne v0,zero,0x8001EC48`, `nop` delay slot, fall-through `0x8001EC5C`; state-specific comparison threshold is 384.
- Frame parity alternates command bases `0x800AD8D0` and `0x800D0048`, stride `0x22778`, once per active frame.
- The 600-VBlank run retained 6,000 bounded events, wrote zero R4 bytes, shut down normally, and left no PCSX process.
- Detailed evidence and limits: `docs/R4_LOOP_PARITY.md`.

## Section 18 — Display/draw pages and bounded GPU command cadence

Date: 2026-07-17 JST

- Official PCSX-Redux Lua docs confirm raw screenshot access but do not document direct current-page, GP0/GP1, GPUSTAT, DMA2, or OT-root getters; no API was guessed.
- Ghidra and dynamic `a0` values identify `0x8009331C` as PutDispEnv, `0x80093150` as PutDrawEnv, and `0x800930E0` as DrawOTag.
- A 240-VBlank real trace confirmed opposing 320×240 display/draw pages at VRAM Y=0/Y=240, switched only on 120 active frames.
- Four OT roots map to the two `0x22778` command arenas. Two lists are submitted per active frame and zero on every duplicate.
- Added PS1 RAM pointer validation, loop detection, payload bounds, 4,096-node cap, 1 MiB byte cap, and address-normalized command hashing.
- All 240 list traversals terminated normally. Primary list content changed on all 120 active frames; the secondary list was structurally stable.
- Every duplicate reused the preceding command identity and screenshot hash. Normal shutdown left no PCSX process and wrote zero R4 bytes.
- The first node-per-IPC prototype was safely interrupted as too slow; cleanup succeeded. A 1,024-node bounded attempt was retained as FAIL and motivated the final 4,096-node cap.
- Detailed evidence and UNKNOWN fields: `docs/R4_GPU_PIPELINE.md`.

## Section 19 — Active overlay call order and side effects

Date: 2026-07-17 JST

- Ghidra re-exported 14 selected base functions; dynamic tracing used only those boundaries plus the overlay entry, 15 breakpoints total.
- Thirty active frames reconstructed identically from CPU-cycle order and overlay delimiters; 544 events stayed far below 2,048 per frame.
- Selected order is timer → early HUD/OT → player/AI dispatcher → camera → stateful animation → camera matrices → render/geometry phases → stateful world effects → HUD animation → audio/static state → GPU submission.
- OT construction starts before vehicle physics and continues later; the path is not a contiguous logic-then-render suffix.
- Stateful animation, static, RNG/audio candidates, and OT writes are interleaved with geometry. The apparent render suffix is excluded from direct re-entry.
- Two isolated HUD primitive builders survive the coarse side-effect exclusion but cannot redraw the 3D scene.
- No render-only boundary is proven; no R4 memory write or patch was attempted.
- Detailed callsites, roles, confidence, side effects, and boundary decisions: `docs/R4_RENDER_BOUNDARY.md`.

## Section 20 — Input normalization and engine-speed candidate

Date: 2026-07-17 JST

- Five state-reloaded Pad override scenarios ran for 120 VBlanks each with a fixed 0x400-byte player-object window and six bounded breakpoints.
- `FUN_8004AA7C` normalizes input once per active frame: `0x8004AD40` writes edge bits at `0x800F3820`, and `0x8004B6C4` writes held bits at `0x800F3822`.
- Dynamic masks: CROSS `0x0040`, LEFT `0x8000`, RIGHT `0x2000`, and CROSS+LEFT `0x8040` in the high halfword. The raw SIO packet remains UNKNOWN.
- `0x800F4A50` is written by vehicle function `FUN_80023924`, read by vehicle logic and the overlay HUD/audio path, and changes once per active frame.
- Its scenario ranges and non-uniform speed correlations support “engine-speed-related candidate”; no calibrated RPM unit is claimed.
- The player object search was strictly limited to 0x400 bytes and retained only ranked field summaries, not object dumps.
- PASS: all five scenarios, zero R4 writes, normal shutdown, no residual PCSX process.
- Details: `docs/R4_INPUT_PATH.md` and `docs/R4_RPM_INVESTIGATION.md`.

## Section 21 — Three-run AI trajectory verification

Date: 2026-07-17 JST

- Added strict active-count and pointer-table validation: 8 unique aligned vehicle objects, verified player first, all fixed field windows inside PS1 RAM.
- Three fresh PCSX processes each ran 600 VBlanks and sampled all eight vehicles every two VBlanks.
- All 900 multi-vehicle samples matched exactly across attempts; each run recorded 300 shared `FUN_80038338` dispatcher hits.
- Every AI changed X/Z/progress on nearly every active sample; orientation and speed changes remained value-dependent.
- Individual trajectories confirm player and seven AI cars are coupled to the 30 Hz dispatcher.
- A player/camera-only interpolation design would leave seven visible AI cars stepped and is therefore incomplete.
- PASS with zero R4 writes, normal shutdown, and no residual PCSX process. Details: `docs/R4_AI_TRAJECTORIES.md`.

## Section 22 — Audio cadence

Date: 2026-07-17 JST

- `FUN_8005006C` and ten major audio sub-updates ran exactly 60 times over 120 VBlanks, only on active integrated frames.
- Engine/audio state setter `FUN_80050368` ran 180 times: one overlay use and two channel uses per active frame.
- Lower SPU voice setters exceeded the 512-hit cap on active VBlanks; exact counts are censored rather than guessed.
- Three CD/XA command/status functions each ran 60/120, confirming game-side XA/BGM control is also active-frame coupled in this state.
- Audio waveform rate is not inferred from game control cadence. Audio updates are excluded from render-only re-entry.
- Details: `docs/R4_AUDIO_CADENCE.md`.

## Section 23 — Replay candidates and existing transform pairs

Date: 2026-07-17 JST

- Bounded runtime probes for `FUN_8002ECD0` and `FUN_8002D3B8` recorded zero hits in the current state; replay analysis remains STATIC_ONLY.
- The mode callback table contains the active overlay and four alternate owned-overlay candidates; `DEMONSTRATION` exists in the base executable.
- Alternate overlay decompilation calls `FUN_8002ECD0`, which reconstructs current XYZ from quarter-scale recorded fields, rebuilds matrices, applies offsets, and copies final XYZ to `+0xC8/+0xCC/+0xD0`.
- A 120-VBlank player/AI probe confirmed `+0xC8/+0xCC/+0xD0` equals same-frame current XYZ on all 60 active samples, not previous-frame XYZ.
- `+0x20/+0x24/+0x28` is a quarter-scale source related to current position, not a retained prior frame. No prior/current pair or interpolation fraction was found.
- Camera scratch XYZ changes only on 60 active frames and remains unchanged on duplicates.
- Details: `docs/R4_REPLAY_PATH.md`; state-pair evidence under ignored `runs/state-pairs/20260716T203519331882Z/`.

## Section 24 — Render candidate schema and interpolation decision

Date: 2026-07-17 JST

- Added strict protocol-1 render candidate model and JSON Schema with exact fields, confidence, and five allowed classifications.
- Four tracked candidates validate: active overlay and post-camera suffix are unsafe; alternate overlay and GPU transformation lack sufficient evidence.
- Existing render XYZ is a same-frame copy, camera scratch is 30 Hz, seven AI require visual treatment, and stateful effects/audio remain interleaved.
- Method A (re-run suffix) is unsafe; B (player/camera only) is incomplete; C (all vehicles/camera shadowing) is conceptually coherent but lacks a safe boundary; D (GPU command mutation) cannot reconstruct camera-aware geometry.
- No code injection, code cave, RAM address, replacement instruction, or patch manifest was created.
- Final classification: **RESULT_C — integrated too strongly with current evidence**.
- Additional state plan is documented but no new state is requested in this phase.
- Details: `docs/R4_INTERPOLATION_FEASIBILITY.md` and `docs/R4_RENDER_BOUNDARY_CANDIDATES.json`.
