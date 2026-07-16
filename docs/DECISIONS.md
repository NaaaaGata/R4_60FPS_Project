# Design decisions

## ADR-001: Standard-library core

The MVP uses `argparse`, `dataclasses`, `tomllib`, `sqlite3`, and JSONL. This minimizes runtime dependencies and keeps the safety layer inspectable. `pytest` and `mypy` are development-only dependencies.

## ADR-002: Fake adapter is the default

Commands default to deterministic fake execution. Real emulator activity requires explicit configuration. This allows CI and first-run validation without BIOS or game assets and prevents accidental writes to a running emulator.

## ADR-003: SQLite index plus JSONL telemetry

SQLite stores experiment identity, lifecycle, summaries, and comparisons. High-volume telemetry remains append-oriented JSONL. Parquet is deferred until measured trace volume justifies a dependency.

## ADR-004: One checked RAM change per experiment

The validator defaults to one aligned change inside PS1 main RAM, requires exact original bytes and restoration data, and rejects unverified target identity. Multi-change support is intentionally absent from the MVP.

## ADR-005: Loopback TCP for the PCSX-Redux bridge

Phase 3A uses a Python server bound exactly to `127.0.0.1` and a Lua/Luv client. This is directly testable, avoids filesystem polling races, supports request timeouts and asynchronous VBlank events, and can be closed from the PCSX-Redux `Quitting` event. A random per-process token prevents an unrelated local process from completing the handshake. Reconnection is deliberately not automatic; disconnect is a terminal capability failure.

## ADR-006: Raw screenshots and explicit raw save states

PCSX-Redux returns screenshot pixels as a Slice, so Phase 3A writes bounded raw data plus JSON metadata without adding an image dependency. Lua save-state APIs use uncompressed protobuf data while UI states are gzip-compressed; the bridge accepts only explicitly named `.rawstate` files and rejects ambiguous/UI formats.

## ADR-007: Deterministic input uses the emulator Pad override API

Input replay uses PCSX-Redux's documented `PCSX.SIO0.slots[1].pads[1].setOverride` and `clearOverride` methods. This keeps input VBlank-aligned and inside the emulator process, avoids macOS accessibility permissions and timing jitter from OS-level events, and permits explicit release in every cleanup path. Input definitions are bounded JSON data with canonical SHA-256 identities; no new runtime dependency is added.
