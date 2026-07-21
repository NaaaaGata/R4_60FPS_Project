# RecompOne compatibility

Date: 2026-07-22 JST
Scope: phases R0–R3 only; no RecompOne runtime boot

## Toolchain

| Item | Verified result |
|---|---|
| Repository | `https://github.com/BlackLabelHQ/RecompOne` |
| Branch / commit | `master` / `3d8b0e1b6ab7ebf444e8d4d02e6320746ec62807` |
| Commit date | `2026-07-20T15:38:24-03:00` |
| Source state | clean, detached at the pinned commit |
| License | MIT |
| Host | macOS 26.5, arm64 (`osx-arm64`) |
| .NET SDK / runtime | SDK 10.0.201; host/runtime 10.0.5 arm64 |
| Source build | PASS, 0 errors / 4 warnings |
| CLI usage smoke | PASS; no-config invocation printed usage and returned 1 |

The source was built locally from the pinned checkout with:

```bash
dotnet build private/tools/recompone/RecompOne.sln --configuration Release --no-incremental
```

The four warnings are upstream warnings: possible null dereferences in `CdDebugPanel` and `SpuViewerPanel`, an unused `contributors` local in `AboutPopup`, and the assigned-but-unused `LibCd._xaActive` field. No warning was suppressed and the source tree was not modified.

`doctor` treats RecompOne as optional. `recompone-doctor` additionally refuses an unpinned commit, dirty source tree, unverified MIT license, or unsupported .NET version. Discovery accepts `R4_AUTOLAB_RECOMPONE`, `[tools].recompone`, or a `recompone` executable on PATH; the selected value may be a checkout, executable, or recompiler DLL.

## Safe adapter boundary

The RecompOne adapter implements:

- a typed config model plus strict JSON Schema;
- project-contained CUE and function-map paths;
- an output boundary under ignored `private/recompone/generated/`;
- disc-internal overlay path validation and bounded offset/base/size fields;
- mandatory main and overlay function maps;
- rejection of linear sweep, debug mode, stubs, ignored functions, and patches;
- shell-free argument-array launch;
- timeout, maximum captured log size, process-group kill, and residual-child detection;
- CUE/BIN hashes before and after generation;
- generated file, function-map, config, and tool provenance hashes;
- explicit unknown-instruction, unmapped-call, collision, partial-output, and non-zero-exit failure states;
- redacted/relative paths in JSON reports.

Relevant commands are:

```bash
r4-autolab recompone-doctor
r4-autolab recompone-export-funcmap --ghidra-export <export.json> --output <private-map.json>
r4-autolab recompone-generate --recomp-config <private-config.json> --dry-run
r4-autolab recompone-generate --recomp-config <private-config.json>
r4-autolab recompone-compile --recomp-config <private-config.json>
```

## R4 code-generation result

Private owned assets were available, so the R3 smoke used the verified Japanese target `SLPS-01800`, executable SHA-256 `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775`, load `0x80010000`, and entry `0x8007D4B4`. The active race overlay used disc file `R4.BIN`, offset `0x0261A000`, size `0x46000`, base `0x801146F0`, and extracted-overlay SHA-256 `bd8567574ae116f8bf1df7a3282cd44d46b7523bfcd6b2867e0bf1de48aa53cb`.

Ghidra was re-exported after adding contiguous-body metadata. The deterministic maps were:

| Map | Functions | SHA-256 | Classification |
|---|---:|---|---|
| main | 1,456 | `c2caaba8db15b67978a78c63700517336408f8d41f4a3ba50b9f4b9223bf6cc1` | strict conversion |
| race | 503 | `70ba2af106caaae147dd2c030f04c6b42dd12d0e7e4c20f0a6e548f4685d6886` | one 1-byte Ghidra pseudo-function explicitly classified and omitted |

The race export contained one function at `0x80119718` whose contiguous range was one byte, so it cannot represent a 32-bit MIPS instruction. Strict conversion failed first. A separate explicit `--exclude-invalid-functions` run omitted only this structurally invalid entry and recorded `omitted_invalid_functions=1`; no function was stubbed or ignored in the RecompOne config.

Code generation exited 0 and emitted 1,959 C# functions: main 1,456 and race 503. RecompOne reported main jump tables in 68 functions / 979 entries and race jump tables in 1 function / 1 entry. It applied zero reimplementations. Configured stubs, ignored functions, and patches were all zero.

Generation is nevertheless **FAIL** because the log contains two unknown instructions:

```text
[Unknown] SPECIAL fn=0x0B word=0x0000000B @ 0x801166F0
[Unknown] op=0x18 word=0x61726167 @ 0x8011DEF4
```

Both addresses map into embedded text/data in the overlay image. The first address is also the target of direct `jal` instructions in the original MIPS, so it cannot safely be discarded as unreachable data. The second lies inside Ghidra's `FUN_8011DEDC` and runs into an ASCII marker. This is a function-boundary/instruction-semantics fidelity blocker, not evidence about R4 timing.

The adapter also scans generated C# rather than relying only on the generation log. It found 427 unique `Dispatcher.Call` targets that are absent from every emitted dispatch table. RecompOne logged zero runtime unmapped-call errors only because runtime was not started; the report therefore records 427 static unmapped-call candidates. Many are continuation addresses created around Ghidra body boundaries, and one is the clearly implausible external target `0x88C1959C` emitted from the data-like `FUN_8011DEDC`. These candidates independently fail G1 even if the two unknown comments were removed.

The generated private project compiled successfully with 0 errors and the same 4 upstream runtime warnings. This proves syntactic C# generation and Runtime project compatibility, but comments replacing unknown instructions mean compile success does not pass fidelity gate G1.

Source hashes remained unchanged:

| Asset | Before / after SHA-256 |
|---|---|
| CUE | `139eedfa188f0612f30bca2c0e9fb6d2fdbfd2502a9dc71fceafd73da3011e95` |
| BIN | `72e54ea4bf6da5a2e839a355e9dcacae989fcddcab84b85cbbb4b2ff08f4a716` |

No RecompOne/R4Generated process remained. The runtime was not started, and R4 memory writes, replacements, patches, frame-wait changes, and 60 fps experiments were all zero.

## Current gate and resume procedure

G0 Toolchain is PASS. G1 Codegen is FAIL because static output contains two unknown instructions and 427 unresolved dispatch targets, although generated compile is PASS. Gates G2–G7 are not entered.

The next safe step is a bounded static investigation of the two original MIPS locations, their callers, and the unresolved continuation targets, followed by upstream-general fixes demonstrated with game-free synthetic fixtures or corrected evidence-backed function boundaries. Re-run generation and require unknown instruction count 0, unmapped calls 0, collisions 0, compile PASS, unchanged asset hashes, and no residual process. Do not boot the runtime before all G1 conditions pass.
