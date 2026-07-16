# R4 GPU pipeline and buffer evidence

Scope: verified `SLPS-01800` executable and captured race state only. The real run used 240 VBlanks of `accelerate-straight-600`, a read-only PCSX session, four bounded Exec breakpoints, fixed command arenas, and zero R4 memory writes.

## Result

R4 uses two 320×240 16-bit VRAM pages and switches them only on each active 30 Hz iteration. The display page and draw page are always opposite:

| Active parity | Display environment | Draw environment | Command arena |
|---|---|---|---|
| A | `(0,240) 320×240` | clip `(0,0) 320×240`, offset `(0,0)` | `0x800AD8D0` |
| B | `(0,0) 320×240` | clip `(0,240) 320×240`, offset `(0,0)` | `0x800D0048` |

`rgb24=0` and `interlace=0` in both `DISPENV` instances. On all 120 intervening duplicate VBlanks, display ID, draw ID, command roots, command hash, and screenshot hash reused the preceding active values, with zero GPU submission calls.

## API and static identification

The official PCSX-Redux Lua documentation exposes `PCSX.GPU.takeScreenShot()`, returning raw pixels, dimensions, and BPP. It does not document direct Lua getters for GP0, GP1/GPUSTAT, current display/draw pages, DMA channel 2, or the current OT root. No such API was guessed.

The fallback is evidence-backed PsyQ code:

| Function | Static behavior | Dynamic `a0` |
|---|---|---|
| `0x8009331C` | `PutDispEnv` equivalent | command base + `0x5C` |
| `0x80093150` | `PutDrawEnv` equivalent | command base |
| `0x800930E0` | `DrawOTag` equivalent | command base + `0xB6C`, then `+0x166C` |

The first two structures are decoded only at those captured pointers. Display/draw IDs are therefore **DYNAMIC_CONFIRMED** for this path. Direct GPU status, DMA channel registers, field status, and raw GP0/GP1 state remain **UNKNOWN**.

Official references: [PCSX-Redux basic Lua GPU API](https://pcsx-redux.consoledev.net/Lua/redux-basics/) and [PCSX-Redux rendering pipeline](https://pcsx-redux.consoledev.net/Lua/rendering/).

## Bounded ordering-table hashes

Each active frame supplied two `DrawOTag` roots:

| Command arena | Primary root | Secondary root |
|---|---|---|
| `0x800AD8D0` | `0x800AE43C` | `0x800AEF3C` |
| `0x800D0048` | `0x800D0BB4` | `0x800D16B4` |

Traversal interprets the high header byte as command-word count and low 24 bits as the next pointer. It validates every pointer against 2 MiB PS1 RAM, checks each payload end, detects loops, and stops at 4,096 nodes or 1 MiB. A command arena is read in three requests no larger than 65,536 bytes; the few nodes outside it are read individually under the same total traversal bounds. No arena bytes are retained in the report.

All 240 traversals (two lists × 120 active frames) reached the `0xFFFFFF` terminator:

| List | Nodes | Command words | Content behavior |
|---|---:|---:|---|
| Primary | 1,588–1,846 | 6,390–8,782 | 120 unique normalized hashes / 120 active frames |
| Secondary | exactly 706 | exactly 8 | one normalized hash across 120 active frames |

The normalized hash excludes RAM addresses/link pointers and includes ordered command counts and command payload words. The identity hash also includes physical node/link identity. Each duplicate VBlank reuses the immediately preceding identity hash because no new `DrawOTag` call occurs. This establishes command generation/submission at 30 Hz and command-list inactivity at the intervening VBlank.

The two lists are structurally distinct, but assigning them to “3D” and “HUD” would be speculation. Their semantic split is **UNKNOWN** pending bounded producer/call-order evidence.

## Ordering

Within the base main loop, Ghidra places the race overlay call before `PutDispEnv`, `PutDrawEnv`, and both `DrawOTag` calls. Dynamic CPU-cycle events confirm recurring camera events have a later GPU submission, but pause-per-VBlank collection can group the tail of one frame with the start of the next. Exact overlay-internal producer ordering is therefore deferred to the dedicated call-order trace.

## Reproduction

```bash
r4-autolab trace-gpu-buffers \
  --vblanks 240 --scenario accelerate-straight-600 \
  --max-nodes 4096 --max-bytes 1048576 --max-events 10000

r4-autolab gpu-command-cadence \
  --vblanks 240 --max-nodes 4096 --max-bytes 1048576
```

PASS evidence is under ignored `runs/gpu-buffers/20260716T200529966325Z/`: 240 samples, 600 bounded events, 240 list submissions, all traversal statuses `terminator`, normal shutdown, and no residual PCSX process.
