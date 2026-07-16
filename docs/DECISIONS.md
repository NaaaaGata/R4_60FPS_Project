# Design decisions

## ADR-001: Standard-library core

The MVP uses `argparse`, `dataclasses`, `tomllib`, `sqlite3`, and JSONL. This minimizes runtime dependencies and keeps the safety layer inspectable. `pytest` and `mypy` are development-only dependencies.

## ADR-002: Fake adapter is the default

Commands default to deterministic fake execution. Real emulator activity requires explicit configuration. This allows CI and first-run validation without BIOS or game assets and prevents accidental writes to a running emulator.

## ADR-003: SQLite index plus JSONL telemetry

SQLite stores experiment identity, lifecycle, summaries, and comparisons. High-volume telemetry remains append-oriented JSONL. Parquet is deferred until measured trace volume justifies a dependency.

## ADR-004: One checked RAM change per experiment

The validator defaults to one aligned change inside PS1 main RAM, requires exact original bytes and restoration data, and rejects unverified target identity. Multi-change support is intentionally absent from the MVP.

