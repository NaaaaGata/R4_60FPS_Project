# Final implementation audit

This audit distinguishes implemented infrastructure from external evidence that does not yet exist. Completing the automation framework does not imply a successful R4 60 fps patch.

## Environment acceptance

| Requirement | Result | Evidence |
|---|---|---|
| One-command diagnostics | PASS | `r4-autolab doctor` |
| Reproducible fake baseline/candidate | PASS | SQLite runs, JSONL traces, deterministic tests |
| Explicit real PCSX connection | PASS | `pcsx-capabilities` real smoke |
| VBlank telemetry, PC/RA/SP/GPR/watch values | PASS | Lua host and boot observation |
| Screenshots linked to run IDs | PASS | raw data + JSON metadata |
| Checked RAM patch and restoration | PASS in fake; real scratch SKIP | No operator-confirmed scratch location |
| Baseline/candidate comparison | PASS | threshold/cadence/trajectory evaluator |
| SQLite lifecycle history | PASS | experiments, transitions, comparisons, campaigns |
| Crash/freeze/timeout surfaces | PARTIAL | deterministic flags/timeouts exist; broader real fault injection remains |
| Asset-free CI tests | PASS | 42 tests |
| Ghidra bridge | PASS fake / BLOCKED real | `analyzeHeadless` absent |
| Codex loop | PASS fake / real disabled | schema/readonly adapter and fake campaign |
| First R4 target identity | PASS | serial, executable hash/header confirmed |
| Deterministic R4 race state | PASS | one-Enter capture and three-process reload validation |
| First R4 race investigation | PARTIAL | deterministic state present; input replay and bounded race traces pending |

## Safety audit

- Original BIN/CUE timestamps and content are not modified by project code.
- Private extracted executable, runs, states, captures, local config, and virtual environment are ignored.
- R4 observation used Read/Write breakpoints and memory reads only; no candidate-address writes occurred.
- Real Codex, real Ghidra, scratch write, 60 fps patch generation, NOP changes, and disc/BIOS changes were not run.
- IPC binds exactly to `127.0.0.1`, authenticates a per-process token, limits messages, and enforces timeouts.
- External processes use argument arrays and bounded shutdown/kill cleanup.

## Final verification snapshot

Date: 2026-07-17 JST

- `pytest`: 42 passed.
- `mypy src`: success for 28 source files.
- `doctor`: PCSX-Redux `4ad775e47d47cc9023aa45a2f439289c5897801a` detected; Ghidra absent.
- Extended real PCSX capability: all requested read-only and state/breakpoint checks PASS; scratch SKIP; no child remains.
- Fake Ghidra export: PASS.
- Campaign dry-run and Fake Codex execution: PASS, game-speed ratio 1.0.
- `git diff --check`: clean before this audit commit.

## 60 fps research status

No 60 fps candidate exists, and none should be generated from the boot trace. Success criteria requiring 58+ distinct real R4 render states/s, race timer/physics/AI/lap integrity, multiple courses/views, CPU overclock recording, and replay compatibility remain wholly untested.

## Exact external resume requirements

1. Implement and verify a deterministic controller-override sequence from the official PCSX-Redux Pad API.
2. Register the verified local Ghidra installation and real-smoke the export script.
3. Run bounded race observation for the frame and vehicle Write PCs, then bounded render-time Read PCs.
4. Map only captured PCs to functions/xrefs and classify update loops.
5. Only after evidence exists, consider one RAM-only candidate with expected bytes and full restoration.

The repository is therefore complete for the automation and boot-observation work executable in the current environment, while race-level and 60 fps conclusions are explicitly blocked rather than fabricated.
