# R4 AutoLab

Current phase-by-phase implementation status is tracked in [PROGRESS.md](PROGRESS.md).
The current-environment acceptance matrix and external blockers are in [docs/FINAL_AUDIT.md](docs/FINAL_AUDIT.md).

R4 AutoLab is a reproducible, safety-first experiment supervisor for researching the PlayStation game *R4 -RIDGE RACER TYPE 4-*. Its purpose is to measure the relationship between VBlank, rendering, physics, AI, timers, and buffers before any 60 fps patch is attempted.

The current MVP provides an asset-free fake experiment path plus a verified PCSX-Redux bridge: configuration, diagnostics, input/disc identity inspection, SQLite lifecycle history, JSONL telemetry, checked RAM patching and restoration, baseline/candidate evaluation, reporting, localhost Lua/JSONL IPC, raw screenshots, and raw save-state capture/reload. It does **not** claim a real-game 60 fps patch.

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
r4-autolab pcsx-capabilities
r4-autolab pcsx-capabilities --include-breakpoint-smoke --include-save-state-roundtrip
r4-autolab ghidra-export --input /private/path/PSX.EXE --address 0x80010000 --fake
r4-autolab visual-check --raw screenshot.raw --metadata screenshot.json
r4-autolab init-config
r4-autolab inspect-input /path/to/owned/file
r4-autolab inspect-disc --cue /path/to/owned/disc.cue --extract-directory private/extracted
r4-autolab capture-manual-state --name race-straight
r4-autolab r4-observe --cue /path/to/owned/disc.cue --vblanks 600
r4-autolab baseline --scenario fake-straight
r4-autolab experiment --proposal config/fake_candidate.example.json
r4-autolab compare <baseline-id> <experiment-id>
r4-autolab trace-summary <run-id>
r4-autolab report <run-id>
r4-autolab campaign --config config/budgets.example.toml
r4-autolab campaign --config config/budgets.example.toml --execute --fake-codex
r4-autolab stop
```

Use `--config /path/to/project.toml` before the subcommand to select another project configuration.

## Private asset setup

Never commit a disc image, BIOS, executable, save state, or raw capture. Store them in ignored directories (`private/`, `input/`, `states/`, or `captures/raw/`) or outside the repository. `inspect-input` emits only filename, size, SHA-256, format, and direct PS-X EXE header metadata; it does not dump content.

The manual capture command auto-detects a verified private R4 Japanese CUE, starts PCSX-Redux without test mode, and waits for one Enter press before pausing and saving ignored raw artifacts. It then performs three fresh-process reload checks and updates only ignored `config/project.toml`. See [manual state capture](docs/MANUAL_STATE_CAPTURE.md), [PCSX-Redux compatibility](docs/PCSX_REDUX_COMPATIBILITY.md), [setup](docs/SETUP.md), [experiment protocol](docs/EXPERIMENT_PROTOCOL.md), and [safety policy](docs/SAFETY.md).

## Current limitations

- Phase 3A is verified against the local arm64 PCSX-Redux build documented in `docs/PCSX_REDUX_COMPATIBILITY.md`; other builds may differ.
- Real Codex execution remains disabled until a separately audited, non-zero budgeted configuration is introduced.
- Ghidra real smoke, deterministic controller replay, and GPU/VRAM hashing remain pending.
- The R4 Japanese disc identity is confirmed, but known runtime addresses still require race-state evidence.
