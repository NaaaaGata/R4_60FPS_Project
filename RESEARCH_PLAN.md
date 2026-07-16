# R4 AutoLab research plan

## Status and evidence rules

This repository begins with no verified executable serial, hash, load address, save state, or emulator bridge. The addresses in `Agents.md` are hypotheses until the target executable and runtime behavior are verified. Every research record must label claims as **hypothesis**, **observation**, **inference**, or **confirmed**.

The original disc image is immutable input. Initial modifications are RAM-only, checked against an executable hash and expected original bytes, and restored after every experiment.

## Work sequence

1. Build and test the asset-free supervisor, SQLite store, state machine, patch safety checks, evaluator, fake emulator, and JSONL IPC.
2. Diagnose the local toolchain and inspect only metadata/hashes of private inputs.
3. Connect PCSX-Redux through a versioned localhost/file JSONL bridge and prove load-state, VBlank stepping, telemetry, screenshot, patch, and restoration operations independently.
4. Record a deterministic baseline from a user-provided save state and input script.
5. Verify candidate runtime addresses and locate their write/read PCs before proposing any patch.
6. Export only relevant MIPS functions and xrefs from Ghidra, retaining instruction/decompiler correspondence.
7. Run one-variable candidate experiments with hard budgets, compare timing/physics/rendering/stability, and retain failures.

## MVP acceptance

- `doctor`, configuration initialization, input metadata inspection, fake baseline/experiment, comparison, summary, report, campaign dry-run, and stop commands work.
- Every experiment records state transitions and summary data in SQLite and telemetry in JSONL.
- Patch application refuses mismatched bytes or unsafe addresses and restoration runs on both success and failure.
- Unit and integration tests require no copyrighted assets or external emulator.

## Resume point for real assets

After installing PCSX-Redux and preparing a private BIOS, verified disc image, save state, and deterministic input script, copy the example configuration outside version control, set `mode = "real"`, and first run bridge capability tests. Do not begin address patching until input metadata and executable identity are stored with the run.

