# Final implementation and race-analysis audit

Date: 2026-07-17 JST. This audit distinguishes infrastructure, one verified race-state timing model, and absent 60 fps evidence. No 60 fps patch is claimed.

## Target and reproducibility

| Item | Result |
|---|---|
| Target | R4 Japanese `SLPS-01800` |
| Executable SHA-256 | `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775` |
| Load / entry | `0x80010000` / `0x8007D4B4` |
| State | `states/manual-race-20260716T171240718201Z/race_straight.rawstate` (ignored) |
| State SHA-256 | `a80f4a2c1dead74c41e309fe0762b397e635e390ba46ce8251f016b3c595c1e7` |
| State size | 19,063,530 bytes |
| State reload | PASS in three fresh PCSX processes; identical initial/final hashes and 60-VBlank trajectory |
| Deterministic input | official Lua Pad `setOverride` / `clearOverride`; five scenarios × three attempts PASS |
| Source integrity | CUE/BIN hashes unchanged before/after capture |

## Environment acceptance

| Requirement | Result | Evidence |
|---|---|---|
| One-command diagnostics | PASS | `r4-autolab doctor` |
| Authenticated localhost IPC | PASS | protocol 1, request IDs/sequences/timeouts/size checks |
| VBlank, counters, registers, safe reads | PASS real | extended PCSX capability |
| Breakpoint lifecycle | PASS real | Exec/Read/Write implementation and non-firing smoke |
| Raw screenshot | PASS real | dimensions/depth/raw bytes/metadata |
| Raw save-state create/load | PASS real | 19,026,137-byte final roundtrip smoke |
| Process cleanup | PASS real | no child after all final smoke runs |
| Static analysis | PASS real | official Ghidra base executable and race overlay imports |
| Scratch restoration | PASS narrow scope | audited `0x1F8003FC`, paused transient write/read/restore only |
| Automated evaluation | PASS infrastructure | cadence, trajectories, visual checks, SQLite/reporting |
| Real Codex proposal gate | PASS | one signed CLI call, strict schema, zero emulator experiments |
| Asset-free tests | PASS | 102 pytest tests; mypy clean for 45 source files |

## Dynamic address results

The public frame/player/speed/RPM candidates `0x800AC064`, `0x800AC0D0/D4/D8`, `0x800AC104`, `0x800AC288`, and `0x800AC32C` remained zero over a moving 600-VBlank race and had no bounded accesses in their configured phases. They are disproven for this state/build and were never write targets.

`0x801FFF58` changed at approximately 30 Hz, but is a reused stack slot. Dynamic sources include `0x80050194/0x800501B0` and `0x80084C28/0x80084D2C`; Ghidra maps them to `sw/lw ra,0x10(sp)` and `sw/lw s4,0x20(sp)`. Its public camera label is rejected.

Static-guided player object `0x800FFA00 -> 0x800ABCE0` produced real fields:

| Field | Address | Result / bounded Write PCs |
|---|---|---|
| X | `0x800ABCF0` | 299/600 changes, 30.013 Hz; `0x800248B8`, `0x80024A58`, `0x80029438` |
| Y | `0x800ABCF4` | 155/600; `0x80029158`, `0x80029168`, `0x80029464` |
| Z | `0x800ABCF8` | 299/600, 30.013 Hz; `0x800248C0`, `0x80024A60`, `0x80029494` |
| Orientation | `0x800ABD30/34/38` | value-dependent; writers `0x8002935C`, `0x80025028`, `0x8002556C`, `0x80029374` |
| Speed-related | `0x800ABEB8` | 267/600 changes; `0x800244DC`, `0x80024AFC` |
| Rank / lap | `0x800ABECE` / `0x800ABF8A` | stable 7 / 1 during sample; rank writer bounded |
| Progress | `0x800ABE64/68` | second component updated every active frame; writers `0x8002682C`, `0x80027B78` |

Read-PC separation for the original public candidates yielded zero events because they were invalid. Actual object consumers are statically and dynamically correlated through the vehicle/AI dispatcher and camera transform; exhaustive per-field Read PCs remain an explicit unresolved item.

## Timing model

Classification: **E — integrated 30 Hz loop**.

| Subsystem | Evidence | Cadence |
|---|---|---:|
| VBlank | PCSX `GPU::Vsync` | ~60 Hz |
| Base main loop | `0x8001EB88`, `0x8001EC30`, `0x8001EC5C` | 300/600, 30 Hz |
| Race overlay | `0x80114780` | 300/600, 30 Hz |
| Vehicle/AI dispatcher | `0x80038338` | 300/600, 30 Hz |
| Vehicle phases | `0x80029908`, `0x80022EC8` | 60/120 each, 30 Hz |
| Camera | `0x80034178` | 300/600, 30 Hz |
| Lap/timer | `0x8003C838` | 60/120, 30 Hz |
| GPU submit A/B | `0x8009331C`, `0x80093150` | 60/120 each, 30 Hz |
| GPU submit C | `0x800930E0` | twice on each of 60/120 active frames |
| Displayed raw image | 121 consecutive screenshot SHA-256 values | 60/120 transitions, 29.97 Hz |

The raw image sequence is an initial sample followed by exact two-VBlank runs, with duplicate transition ratio 0.50. Physics/AI, camera, timer, GPU submission, and display changes are coupled. No separate 60 Hz rendering path is proven. Detailed ranges, file offsets, calls, pseudocode, and limits are in `docs/R4_TIMING_MODEL.md`.

## Write and candidate audit

- No R4 address, executable instruction, disc, BIOS, or save state was patched.
- Scratch candidate `0x1F8003FC` had zero Read/Write hits and no natural changes across five scenarios / 1,920 VBlanks, twice.
- The first File API scratch attempt failed read-back, ran restoration/cleanup, and remains FAILED evidence.
- The documented scratch pointer retry verified `00000000 -> a5a5a5a5 -> 00000000`; shutdown and cleanup passed.
- Evidence-backed 60 fps candidates: zero. R4 candidate experiments: zero.
- Baseline displayed-image rate: 29.97 Hz. Candidate frame rate and game-speed ratio are not applicable because no candidate ran.

## Real Codex campaign

The final campaign used code-signed Codex CLI 0.144.5 with one call, one proposal, 300 seconds maximum, one-change maximum, non-zero finite accounting budget, ephemeral read-only sandbox, ignored user configuration, disabled web search, and strict JSON Schema output. Codex returned `changes=[]`; the evidence gate recorded `NO_SAFE_CHANGE`. PCSX launches and RAM writes were both zero.

Two preceding schema-compatibility failures are recorded as FAILED with exact ignored logs and zero emulator experiments. They resulted in a strict Structured Outputs-compatible schema.

During diagnosis, macOS blocked stale Homebrew Codex 0.125.0 due an invalid signature. It was not bypassed or used. The final campaign explicitly selected the separate VS Code Codex 0.144.5 binary after strict code-signature verification. OpenAI's current security notice recommends updated official builds only.

## Tool versions and final checks

- PCSX-Redux changeset: `4ad775e47d47cc9023aa45a2f439289c5897801a` (arm64).
- Lua: 5.1; LuaJIT: 2.1.1739213504; interpreter/debugger acknowledged.
- Ghidra: official NSA 12.1.2, ZIP SHA-256 `b62e81a0390618466c019c60d8c2f796ced2509c4c1aea4a37644a77272cf99d`.
- Java: OpenJDK 21.0.11.
- Codex: 0.144.5, macOS code signature valid.
- `pytest`: 102 passed.
- `mypy src`: success, 45 source files.
- `doctor`: all required/optional configured tools detected.
- Extended `pcsx-capabilities`: all requested checks PASS; scratch intentionally SKIP in final read-only smoke because its separate explicit proof already passed.
- Real campaign budget dry-run: PASS.
- `git diff --check`: clean before final audit commit.

## GitHub delivery

- Prior branch: `feat/race-state-analysis`, Draft PR #1.
- Render-boundary branch: `feat/render-boundary-analysis`.
- Render-boundary base: `feat/race-state-analysis`.
- Draft PR: `https://github.com/NaaaaGata/R4_60FPS_Project/pull/2`.
- Phase commits through this audit include `5ffc2e3`, `353ad25`, `c24876e`, `8182590`, `67044c9`, `aaec8e8`, and `9ca48a0`; final audit/campaign commit follows this document.

## Unresolved work

Raw SIO parsing/analog scalars, exact RPM units, runtime replay reachability/compatibility, safe previous/current shadow ownership, other courses/views, and CPU overclock needs remain unresolved. The exact wait branch, parity, display/draw IDs, bounded GPU hashes, digital input path, engine-speed candidate, individual AI trajectories, audio cadence, and static replay transform candidate are now documented. Remaining gaps still prohibit a 60 fps patch claim.

The next safe step is more bounded observation and static correlation of those items. It is not a RAM patch, frame-wait removal, NOP, or broad address search.

## Reproduction commands

```bash
source .venv/bin/activate
pytest
mypy src
r4-autolab doctor
r4-autolab replay-input --attempts 3 --sample-every 60
r4-autolab trace-race --vblanks 600 --breakpoint-vblanks 120 --max-hits 32
r4-autolab trace-functions --address 0x80038338 --address 0x80034178 --address 0x8003C838 --vblanks 600 --max-hits 512
r4-autolab trace-addresses --watch player_x:0x800ABCF0:4 --watch player_z:0x800ABCF8:4 --watch speed_field:0x800ABEB8:2 --vblanks 600
r4-autolab render-cadence --vblanks 120
r4-autolab audit-scratch --address 0x1F8003FC --timeout 60
r4-autolab pcsx-capabilities --include-save-state-roundtrip --include-breakpoint-smoke
r4-autolab campaign --config config/budgets.real.example.toml
r4-autolab campaign --config config/budgets.real.example.toml --execute --real-codex
git diff --check
```

## Render-boundary final audit

The read-only render-boundary phase used state SHA-256 `a80f4a2c1dead74c41e309fe0762b397e635e390ba46ce8251f016b3c595c1e7` throughout and never ran the scratch write option.

| Requirement | Result | Evidence |
|---|---|---|
| Exact 30 Hz gate | DYNAMIC_CONFIRMED | `0x8001EC54 bne`, `0x8001EC58 nop`, threshold 384, bounded outcomes |
| Active/duplicate parity | PASS | exact 300/300 alternation over 600 VBlanks |
| Display/draw pages | DYNAMIC_CONFIRMED | opposing `(0,0)` / `(0,240)` 320×240 pages |
| GPU command cadence | PASS | 240 bounded list traversals; 120 primary hashes; zero duplicate submissions |
| Overlay call order | PASS | identical selected 15-function order over 30 active frames |
| Side-effect isolation | FAIL for re-entry | timer/physics/AI/animation/RNG/audio/static/OT work interleaved |
| Input path | DYNAMIC_CONFIRMED digital | frame-post producer and CROSS/LEFT/RIGHT held masks |
| RPM | UNKNOWN exact unit | engine-speed/HUD/audio candidate dynamically confirmed |
| AI trajectories | PASS | 8 vehicles × 300 samples × 3 fresh processes, exact signatures |
| Audio cadence | DYNAMIC_CONFIRMED | top-level and CD/XA control at 60/120 active VBlanks |
| Replay | STATIC_ONLY | alternate callbacks and recorded-transform function; zero runtime hits |
| Previous/current transforms | FAIL for existing pair | render XYZ is same-frame copy; no prior frame or alpha found |
| Candidate schema | PASS | strict protocol-1 model/schema and tracked RESULT_C artifact |
| R4 memory writes | 0 | Python and Lua read-only enforcement; all reports record zero |

Final decision: **RESULT_C — integrated too strongly with current evidence**. There is no `SAFE_RENDER_BOUNDARY`, and RESULT_B is not met because a complete prior/current set and side-effect-free insertion point do not exist. No patch, NOP, branch change, VSync change, frame-counter change, command-list mutation, or RAM experiment is authorized.

Design-only alternatives and future state priorities are in `docs/R4_INTERPOLATION_FEASIBILITY.md`. The next safe work remains read-only multi-scene observation or clearly labelled emulator-side presentation interpolation research.
