# R4 AutoLab

Current phase-by-phase implementation status is tracked in [PROGRESS.md](PROGRESS.md).
The current-environment acceptance matrix and external blockers are in [docs/FINAL_AUDIT.md](docs/FINAL_AUDIT.md).

R4 AutoLab is a reproducible, safety-first experiment supervisor for researching the PlayStation game *R4 -RIDGE RACER TYPE 4-*. Its purpose is to measure the relationship between VBlank, rendering, physics, AI, timers, and buffers before any 60 fps patch is attempted.

The current MVP provides an asset-free fake experiment path plus a verified PCSX-Redux bridge: configuration, diagnostics, input/disc identity inspection, SQLite lifecycle history, JSONL telemetry, checked RAM patching and restoration, baseline/candidate evaluation, reporting, localhost Lua/JSONL IPC, raw screenshots, and raw save-state capture/reload. An experimental RecompOne backend now provides pinned-tool detection, safe private configuration, deterministic Ghidra function-map conversion, bounded code generation, and generated-C# compilation. It does **not** claim a real-game 60 fps patch.

## Five-minute fake demo

Python 3.11 or newer is required. From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/r4-autolab doctor
.venv/bin/r4-autolab init-config --force
.venv/bin/r4-autolab baseline --scenario fake-straight --id baseline-demo
.venv/bin/r4-autolab experiment --proposal config/fake_candidate.example.json
.venv/bin/r4-autolab compare baseline-demo candidate-fake-render-60hz
.venv/bin/pytest
```

The fake candidate intentionally changes only render cadence. For 120 VBlanks, the expected comparison is game-speed ratio `1.0`, zero vehicle/RPM deltas, more unique GPU states, and fewer duplicate frames. This validates the laboratory plumbing, not the game.

Generated artifacts are under `runs/<run-id>/`; SQLite is `runs/experiments.sqlite3`. Both are ignored by Git.

## Common commands

```bash
r4-autolab doctor
r4-autolab recompone-doctor
r4-autolab recompone-export-funcmap --ghidra-export runs/static-cache/<id>/export.json --output private/recompone/function-maps/main.json
r4-autolab recompone-generate --recomp-config private/recompone/config/r4.json --dry-run
r4-autolab recompone-generate --recomp-config private/recompone/config/r4.json
r4-autolab recompone-compile --recomp-config private/recompone/config/r4.json
r4-autolab pcsx-capabilities
r4-autolab pcsx-capabilities --include-breakpoint-smoke --include-save-state-roundtrip
r4-autolab ghidra-export --input /private/path/PSX.EXE --address 0x80010000 --fake
r4-autolab visual-check --raw screenshot.raw --metadata screenshot.json
r4-autolab init-config
r4-autolab inspect-input /path/to/owned/file
r4-autolab inspect-disc --cue /path/to/owned/disc.cue --extract-directory private/extracted
r4-autolab capture-manual-state --name race-straight
r4-autolab replay-input --attempts 3 --sample-every 60
r4-autolab trace-race --vblanks 600 --breakpoint-vblanks 120 --max-hits 32
r4-autolab trace-functions --address 0x80038338 --vblanks 600 --max-hits 512
r4-autolab trace-addresses --watch player_x:0x800ABCF0:4 --vblanks 600
r4-autolab probe-overlay --address 0x80114780 --size 64
r4-autolab render-cadence --vblanks 120
r4-autolab audit-scratch --address 0x1F8003FC --timeout 60
r4-autolab r4-observe --cue /path/to/owned/disc.cue --vblanks 600
r4-autolab baseline --scenario fake-straight
r4-autolab experiment --proposal config/fake_candidate.example.json
r4-autolab compare <baseline-id> <experiment-id>
r4-autolab trace-summary <run-id>
r4-autolab report <run-id>
r4-autolab campaign --config config/budgets.example.toml
r4-autolab campaign --config config/budgets.example.toml --execute --fake-codex
r4-autolab campaign --config config/budgets.real.example.toml --execute --real-codex
r4-autolab stop
```

Use `--config /path/to/project.toml` before the subcommand to select another project configuration.

## Experimental RecompOne backend

RecompOne is an optional static-recompilation research backend, not a replacement for PCSX-Redux or Ghidra. Point `R4_AUTOLAB_RECOMPONE` or `[tools].recompone` at a clean checkout of pinned commit `3d8b0e1b6ab7ebf444e8d4d02e6320746ec62807` after building it with .NET 10. Generated C# is game-derived and must remain under ignored `private/recompone/generated/`.

The safe config rejects linear sweep, debug mode, stubs, ignored functions, patches, path escape, and unignored output. Generation records asset hashes and fails on unknown instructions, unmapped calls, collisions, timeout, log overflow, partial output, or residual processes. See [RecompOne compatibility](docs/RECOMPONE_COMPATIBILITY.md), [fidelity status](docs/RECOMPONE_FIDELITY.md), and [architecture](docs/ARCHITECTURE.md).

The first R4 static generation emitted and compiled 1,959 mapped functions, but two race-overlay instructions remain unknown and 427 generated dispatch targets have no emitted table entry. Therefore fidelity gate G1 is FAIL and runtime boot is intentionally not implemented or attempted.

## Private asset setup

Never commit a disc image, BIOS, executable, save state, or raw capture. Store them in ignored directories (`private/`, `input/`, `states/`, or `captures/raw/`) or outside the repository. `inspect-input` emits only filename, size, SHA-256, format, and direct PS-X EXE header metadata; it does not dump content.

The manual capture command auto-detects a verified private R4 Japanese CUE, starts PCSX-Redux without test mode, and waits for one Enter press before pausing and saving ignored raw artifacts. It then performs three fresh-process reload checks and updates only ignored `config/project.toml`. See [manual state capture](docs/MANUAL_STATE_CAPTURE.md), [PCSX-Redux compatibility](docs/PCSX_REDUX_COMPATIBILITY.md), [setup](docs/SETUP.md), [experiment protocol](docs/EXPERIMENT_PROTOCOL.md), and [safety policy](docs/SAFETY.md).

`audit-scratch` is read-only. The separate `pcsx-capabilities --allow-scratch-write --scratch-address ...` path must remain explicitly gated and may be used only after an audit; see [scratchpad safety audit](docs/SCRATCH_AUDIT.md).

## Current limitations

- Phase 3A is verified against the local arm64 PCSX-Redux build documented in `docs/PCSX_REDUX_COMPATIBILITY.md`; other builds may differ.
- Real Codex proposal-only execution is explicitly available with a non-zero finite budget and an empty evidence catalog; it cannot launch a RAM experiment until a reviewed candidate exists.
- Official Ghidra 12.1.2 base/overlay export and deterministic controller replay are connected; a raw screenshot-hash fallback confirms 29.97 Hz displayed-image cadence, while GPU command hashing remains unavailable.
- The R4 Japanese disc identity, active race overlay, player structure, and integrated 30 Hz race loop are confirmed for one captured race state. No evidence-backed render-only 60 fps patch exists yet.
- RecompOne toolchain gate G0 passes, but code-generation gate G1 fails on two unknown race-overlay instructions and 427 unresolved dispatch targets. Generated compile success is not treated as runtime fidelity; runtime/cross-backend phases remain blocked.
