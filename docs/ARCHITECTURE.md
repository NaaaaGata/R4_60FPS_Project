# Architecture

## Boundaries

`r4-autolab` is a Python supervisor and safety boundary. The CLI creates immutable proposals, the supervisor controls lifecycle and cleanup, an emulator adapter performs bounded operations, and SQLite plus per-run artifacts retain the audit trail. Research-agent output never writes emulator memory directly.

```text
CLI / structured proposal
          |
          v
Supervisor -> SafetyValidator -> EmulatorAdapter
    |                                |-- FakeEmulator (CI/default)
    |                                `-- PCSXReduxAdapter boundary
    +-> ExperimentStore (SQLite)
    +-> JSONL telemetry/artifacts
    +-> Evaluator/reporting
    `-> RecompOneAdapter (experimental, static-only at current gate)
          |-- pinned source detector / .NET launcher
          |-- typed private config validator
          |-- Ghidra JSON -> deterministic funcMap
          |-- bounded code-generation process
          `-- generated-C# compiler
```

## Process and data flow

The supervisor records every state transition, prepares a unique run directory, launches the selected adapter, optionally loads state, validates and applies one RAM change, runs a bounded number of VBlanks, collects telemetry, restores original bytes, shuts down, evaluates the run, and commits the terminal status. Cleanup is attempted in `finally` paths.

The initial PCSX-Redux boundary uses newline-delimited UTF-8 JSON. Every message has a protocol version, request ID, kind (`request`, `response`, or `event`), monotonic sequence number, and operation. Python rejects malformed, oversized, unsupported-version, duplicate/out-of-order, and mismatched-response messages. The production transport may be a file pair or localhost socket; it must preserve the same envelope.

Phase 3A selects a localhost-only TCP transport. Python opens an ephemeral listener on `127.0.0.1` before launching PCSX-Redux and passes the endpoint plus a random session token only through the child environment. Lua connects with PCSX-Redux's bundled Luv, validates requests, and dispatches them on the emulator main-loop safety context. Quitting closes the socket. No listener is exposed on LAN interfaces.

The RecompOne path is a separate process boundary because code generation and a future native runtime have different contracts. The current boundary invokes only a pinned recompiler with an argument array. It applies a timeout, captured-output cap, dedicated process group, child cleanup, CUE/BIN before/after hashes, and failure classification for unknown instructions, unmapped calls, overlay collisions, partial output, and non-zero exit. Public reports redact absolute project paths. Runtime startup is deliberately absent until code-generation fidelity gate G1 passes.

Ghidra remains the static-map authority. `R4Export.java` records each function's first contiguous body range; the converter rejects overlap, unaligned ranges, payload escape, malformed hashes/language, and non-deterministic duplicate symbols. Main and overlay maps are separate so VRAM base and disc offset cannot be conflated.

## Artifacts

SQLite is the canonical experiment index and transition history. Each `runs/<run-id>/` directory contains proposal/metadata JSON, telemetry JSONL, logs, and later screenshots/GPU data. RecompOne reports are under ignored `runs/recompone/`; configs, function maps, generated C#, build products, and any future runtime state are under ignored `private/recompone/`. Large copyrighted memory or executable dumps are forbidden.

## Failure behavior

Launch errors become `FAILED`, budget expiry becomes `TIMED_OUT`, explicit stops become `ABORTED`, and safety violations become `QUARANTINED`. A crash after patching still triggers restoration when the adapter remains reachable. The next real launch must verify original bytes before applying another patch. Fake runs exercise these paths without private assets.
