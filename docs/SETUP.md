# Setup

## Asset-free development

Create `.venv`, install `.[dev]`, run `r4-autolab init-config`, then run `pytest` and `mypy src`. The generated `config/project.toml` defaults to `mode = "fake"` and does not require external tools.

`doctor` treats Python 3.11+ as required and reports Git, Codex CLI, PCSX-Redux, Ghidra `analyzeHeadless`, and Java as optional. It never downloads binaries.

## Private real environment

Provide only assets you own. Keep the following outside Git:

- an installed PCSX-Redux executable;
- a compatible private PlayStation BIOS;
- the owned R4 disc image;
- a deterministic save state and input script;
- optionally Ghidra plus Java for static analysis.

Set executable overrides in environment variables rather than committing local paths. Copy `config/project.example.toml`, set the target serial and executable SHA-256 after verification, and keep `mode = "fake"` until the bridge capability suite passes.

## PCSX-Redux resume checklist

1. Record the exact PCSX-Redux version and path from `doctor`.
2. Implement a small `R4_AUTOLAB_HOST` shim mapping that build's documented Lua APIs to `lua/bootstrap.lua`.
3. Supply a `BridgeTransport` for version-1 JSONL and prove request IDs, sequence checks, timeout, disconnect, and flush behavior against the fake protocol tests.
4. Prove pause/resume, load-state, bounded VBlank stepping, memory read-only access, and clean shutdown.
5. Prove a known fake/scratch RAM write is restored after success, timeout, and bridge disconnect before targeting game code.
6. Capture a deterministic baseline and store executable identity with it.

The Phase 3A host shim and capability transport are implemented. Run the read-only smoke test with:

```bash
r4-autolab pcsx-capabilities
```

This command uses bundled OpenBIOS and no game image by default. It stores its report under `runs/capabilities/`. Do not pass `--allow-scratch-write` unless every read-only check passes and an operator has independently confirmed a non-code scratchpad address; an address is never guessed automatically.

General `mode = "real"` experiments remain disabled. Phase 3A capability success does not authorize game loading, breakpoints, patches, or address research.
