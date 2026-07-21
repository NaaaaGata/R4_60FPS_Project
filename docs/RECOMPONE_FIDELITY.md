# RecompOne fidelity status

Date: 2026-07-22 JST

## Evidence level

All current RecompOne findings are `RECOMP_STATIC_ONLY`. The authoritative PCSX-Redux baseline remains the verified `SLPS-01800` integrated 30 Hz loop documented in `FINAL_AUDIT.md`, `R4_TIMING_MODEL.md`, and `R4_RENDER_BOUNDARY.md`. No RecompOne runtime sample exists, so nothing is `CROSS_BACKEND_CONFIRMED`.

| Dimension | PCSX/Ghidra baseline | RecompOne result | Status |
|---|---|---|---|
| target identity | executable hash, load, and entry verified | same serial/load/entry accepted before generation | matched statically |
| main function map | Ghidra export | 1,456 deterministic functions | converted |
| race overlay | active at `0x801146F0`, entry `0x80114780` | disc offset/base/size mapped; 503 functions | converted, not executed |
| unknown instruction | original MIPS is authoritative | 2 instructions emitted as comments | mismatch / G1 blocker |
| unresolved dispatch | original target/control flow requires MIPS review | 427 generated call targets absent from dispatch tables | mismatch / G1 blocker |
| generated compile | not applicable | PASS, 0 errors / 4 upstream warnings | syntax only |
| cadence | integrated 30 Hz; 300 active / 300 duplicate | no runtime | SKIP |
| timer / trajectory / AI / camera | authoritative bounded PCSX traces exist | no runtime | SKIP |
| GPU/display | active-frame-only submission/page switch | no runtime | SKIP |
| audio | game-side control at active-frame cadence | no runtime | SKIP |
| cleanup and assets | zero writes, normal cleanup | codegen/compile only; hashes unchanged, no process remains | PASS for R3 |

## What RecompOne added

RecompOne produced a second mechanical representation of 1,959 mapped functions and quantified jump-table discovery separately for the main executable and race overlay. Generated-source validation exposed two unknown instructions and 427 dispatch targets with no emitted table entry before any native boot. The result narrows the next investigation to instruction/function-map semantics and prevents a misleading “it compiled, therefore it is faithful” conclusion.

It has not yet added runtime timing, trajectory, GPU, or render-boundary evidence. A fixed 60 Hz host clock or a future window refresh rate will not be accepted as R4 60 fps evidence.

## Blocked comparison

Cross-backend cadence and trajectory comparison is intentionally SKIP. RecompOne cannot consume the verified PCSX raw state, the R3 output is not instruction-complete, and no deterministic RecompOne race checkpoint or input protocol has passed earlier gates. Creating placeholder runtime telemetry would not provide evidence.

## Promotion criteria

Before runtime work, G1 requires zero unknown instructions on known paths, zero unmapped calls, zero overlay collisions, generated compile PASS, unchanged CUE/BIN hashes, and zero configured stubs/ignored/patches. A later RecompOne runtime observation can be promoted from `RECOMP_RUNTIME_ONLY` to `CROSS_BACKEND_CONFIRMED` only after matching the PCSX target identity, overlay dispatch, function cadence, eight-vehicle trajectory, timer, camera, and GPU/display evidence within declared tolerances.
