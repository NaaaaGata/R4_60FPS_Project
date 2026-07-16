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
    `-> Evaluator/reporting
```

## Process and data flow

The supervisor records every state transition, prepares a unique run directory, launches the selected adapter, optionally loads state, validates and applies one RAM change, runs a bounded number of VBlanks, collects telemetry, restores original bytes, shuts down, evaluates the run, and commits the terminal status. Cleanup is attempted in `finally` paths.

The initial PCSX-Redux boundary uses newline-delimited UTF-8 JSON. Every message has a protocol version, request ID, kind (`request`, `response`, or `event`), monotonic sequence number, and operation. Python rejects malformed, oversized, unsupported-version, duplicate/out-of-order, and mismatched-response messages. The production transport may be a file pair or localhost socket; it must preserve the same envelope.

## Artifacts

SQLite is the canonical experiment index and transition history. Each `runs/<run-id>/` directory contains proposal/metadata JSON, telemetry JSONL, logs, and later screenshots/GPU data. Large copyrighted memory or executable dumps are forbidden.

## Failure behavior

Launch errors become `FAILED`, budget expiry becomes `TIMED_OUT`, explicit stops become `ABORTED`, and safety violations become `QUARANTINED`. A crash after patching still triggers restoration when the adapter remains reachable. The next real launch must verify original bytes before applying another patch. Fake runs exercise these paths without private assets.

