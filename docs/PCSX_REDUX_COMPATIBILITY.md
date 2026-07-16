# PCSX-Redux compatibility: Phase 3A

## Verified local build

| Item | Observed value |
|---|---|
| Executable | `/Applications/PCSX-Redux.app/Contents/MacOS/PCSX-Redux` |
| Mach-O architecture | `arm64` |
| Short version | `4ad775e4` |
| Changeset | `4ad775e47d47cc9023aa45a2f439289c5897801a` |
| Build timestamp | `2026-04-21 03:01:23` |
| Executable SHA-256 | `5fc243eeec316b97763373ce3820e4b3a17ab33ed330beb33bfcd09919f57bca` |
| Lua runtime | `Lua 5.1`, `LuaJIT 2.1.1739213504` |
| CPU mode in capability run | `Interpreted` |
| BIOS used in capability run | PCSX-Redux bundled OpenBIOS; no private BIOS argument |
| Game image used | None |

`--version` and `-version` both returned the same JSON build information. `--help` and `-help` opened the application and did not terminate within five seconds, so flag verification used the [official command-line flag documentation](https://pcsx-redux.consoledev.net/cli_flags/) and an isolated `-exec` probe against the installed build.

## Verified command-line flags

The capability command uses only these documented flags:

```text
-run
-stdout
-lua_stdout
-interpreter
-debugger
-testmode
-portable <capability-run>/portable
-dofile <absolute-path>/lua/bootstrap.lua
```

`-dofile` is the supported mapping to `Support.extra.dofile`; the previous unverified `-lua` flag has been removed. `-testmode` is used only for the isolated capability process. `-bios` and `-iso` are supported by the installed build but are omitted from Phase 3A because bundled OpenBIOS is sufficient and no game is needed. They are emitted by the argument builder only when explicitly configured.

The isolated probe exited with status 0 and logged `CPU type: Interpreted`. The Lua handshake also acknowledged `interpreter=true` and `debugger=true`. The official debugger documentation requires both interpreter and debugger for CPU breakpoints: [debugging introduction](https://pcsx-redux.consoledev.net/Debugging/introduction/) and [breakpoint API](https://pcsx-redux.consoledev.net/Lua/breakpoints/).

## Implemented and verified Lua APIs

The host shim is [lua/pcsx_redux_host.lua](../lua/pcsx_redux_host.lua). It uses documented APIs only:

- `PCSX.Events.createEventListener('GPU::Vsync', ...)` and `PCSX.nextTick(...)` for safe VBlank delivery;
- `PCSX.Events.createEventListener('Quitting', ...)` for socket cleanup;
- `PCSX.pauseEmulator()`, `PCSX.resumeEmulator()`, `PCSX.quit(0)`, and `PCSX.getCPUCycles()`;
- `PCSX.getMemoryAsFile():readAt(...)` / `:writeAt(...)` for clamped emulated-memory access;
- `PCSX.getRegisters()` for PC, RA, SP, GP, A0-A3, V0-V1, S0-S7, and T0-T9;
- `PCSX.addBreakpoint(...)` with retained objects, `pcall` protection, deferred event emission, and `:remove()`;
- `PCSX.loadSaveState(file)` for explicitly uncompressed raw states only;
- `PCSX.GPU.takeScreenShot()` and `Support.File.open(..., 'TRUNCATE')` for raw screenshot output.

References: [events](https://pcsx-redux.consoledev.net/Lua/events/), [safe memory and registers](https://pcsx-redux.consoledev.net/Lua/memory-and-registers/), [execution and screenshot API](https://pcsx-redux.consoledev.net/Lua/redux-basics/), and [File API](https://pcsx-redux.consoledev.net/Lua/file-api/).

## Save-state compatibility

PCSX-Redux's Lua API consumes the uncompressed protobuf representation returned by `PCSX.createSaveState()`. UI-created states are gzip-compressed. Phase 3A deliberately accepts only files named `*.rawstate` and sends format `raw-protobuf`; `.gz` and ambiguous extensions are rejected. Automatic gzip decompression and UI-state conversion remain unimplemented.

## IPC compatibility

Python listens on an ephemeral IPv4 socket bound exactly to `127.0.0.1`; Lua connects through the bundled Luv API. The protocol is JSON Lines version 1 with independent monotonic sequences, request IDs, a per-process session token, one-megabyte message limits, strict JSON rejection, bounded Python timeouts, explicit disconnect behavior, and Quitting cleanup. There is no remote bind and no reconnect loop.

## Real capability result

Latest extended successful report:

```text
runs/capabilities/pcsx-20260716T163234351518Z/capabilities.json
```

Observed PASS results: launch, localhost IPC, authenticated protocol handshake, interpreter/debugger acknowledgment, pause, resume, ten strictly increasing VBlank events, CPU-cycle/VBlank counters, required registers, a four-byte read at `0x00000000` through `getMemoryAsFile`, a 640×478 16-bpp screenshot (611,840 raw bytes), non-firing breakpoint creation/removal, a 19,026,416-byte raw-state create/load roundtrip, normal shutdown, and child-process cleanup. Scratch write was SKIP because it was not requested and no operator-confirmed address was supplied.

Earlier failed reports are retained locally as evidence:

- `pcsx-20260716T160351982518Z`: nested Lua module resolution failed at `experiment_runner.lua:1`, so IPC never connected.
- `pcsx-20260716T160440025201Z`: IPC connected but handshake timed out; request diagnostics were not yet present.
- `pcsx-20260716T160601655422Z`: diagnostics showed handshake parsing succeeded, but a redundant nested `PCSX.nextTick` prevented dispatch.

All failed runs shut down the child process and recorded exact logs. `runs/` remains ignored by Git.

## Not verified in Phase 3A

- No breakpoint was installed against game or BIOS code; only API availability and the required interpreter/debugger mode were verified.
- No save state was loaded.
- The initial optional scratch write was skipped until a separate 1,920-VBlank race audit established a narrowly eligible location.

The installed build's `getMemoryAsFile().writeAt()` acknowledged a scratchpad write but did not change bytes at `0x1F8003FC`. The bridge therefore uses the separately documented `PCSX.getScratchPtr()` only for fully range-checked accesses inside the 1 KiB scratchpad; all other reads/writes retain `getMemoryAsFile()`. See the official [memory and registers API](https://pcsx-redux.consoledev.net/Lua/memory-and-registers/) and [File API](https://pcsx-redux.consoledev.net/Lua/file-api/). The failed capability report is retained locally, including successful restoration and shutdown paths; the corrected retry passed write/read/restore and process cleanup. Details are in [SCRATCH_AUDIT.md](SCRATCH_AUDIT.md).
- No private BIOS, R4 image, R4 address, patch, Ghidra analysis, or automated campaign was used.
- VRAM capture, GPU command logging, PNG conversion, reconnection, and compressed save-state conversion remain outside this phase.
