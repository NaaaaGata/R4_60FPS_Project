# Experiment protocol

## Baseline

A baseline fixes target identity, scenario, save state, deterministic input, VBlank count, watch configuration, emulator settings, and CPU clock. No RAM changes are allowed. The supervisor records all lifecycle states and writes JSONL telemetry, a final screenshot, GPU log, proposal, summary, and report under one run ID.

## Candidate

A candidate is a JSON proposal tied to the same target serial and executable SHA-256. The MVP allows at most one naturally aligned 1/2/4-byte main-RAM change. It requires expected original bytes and an evidence reference. The supervisor reads and compares original bytes immediately before writing.

## Lifecycle and restoration

Normal execution follows:

```text
CREATED -> VALIDATING -> PREPARING -> LAUNCHING -> LOADING_STATE
-> APPLYING_PATCH -> RUNNING -> COLLECTING -> RESTORING
-> EVALUATING -> COMPLETED
```

Any state may terminate as failed, timed out, aborted, or quarantined. Applied bytes are retained in memory as restoration receipts and restored in reverse order. Safety violations and restoration failures are quarantined. A real adapter must verify clean original bytes again before a subsequent experiment.

## Comparison

`compare` reads canonical summaries from SQLite and computes game-timer ratio, final position/speed/RPM deltas, unique GPU-state delta, duplicate-frame-ratio delta, and basic stability. A favorable fake comparison is not evidence of real 60 fps; real acceptance also requires AI, course/viewpoint diversity, GPU/buffer evidence, visual integrity, and replay checks.

## Reproduction

Retain the project configuration, proposal, executable identity, save-state hash, input hash, emulator version, and run artifacts. Never retain the copyrighted executable or unrestricted memory dumps in the repository.

