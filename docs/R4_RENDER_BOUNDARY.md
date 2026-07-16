# R4 race render-boundary analysis

This report applies to the verified Japanese executable and captured straight-race state. It combines the active overlay decompilation with a 30-frame, 15-breakpoint, read-only Exec trace. No R4 RAM write, patch, broad breakpoint set, or unbounded event collection was used.

## Reconstructed active-frame order

All 30 frames produced the same selected-boundary sequence (544 events total):

| Seq. | Function | Role | Important side effects | Confidence |
|---:|---|---|---|---|
| 1 | `0x80114780` race overlay | integrated logic | timer, player/AI, static, OT | high |
| 2 | `0x8003C838` | timer | timer/lap, player, result globals | high |
| 3 | `0x8002C158` | HUD-build | scratch, OT append | medium-high |
| 4 | `0x80020E54` | HUD-build | scratch, OT append | medium-high |
| 5 | `0x80038338` | vehicle/AI | player and AI objects, scratch/static | high |
| 6 | `0x80034178` | camera | camera scratch/static transform | high |
| 7 | `0x8007346C` | animation | world/effect state, RNG/audio candidates | medium-high |
| 8 | `0x8006E078` | render-state-build | view matrices in scratch/static | medium-high |
| 9 | `0x8002E808` | unknown selected phase | static state | low |
| 10 | `0x8006EBB4` | geometry-transform | scratch/static, OT | medium |
| 11 | `0x80074680` | geometry/effects | animation, RNG/audio, scratch/static, OT | medium-high |
| 12 | `0x80037584` | camera/track lookup | scratch/static | medium |
| 13 | `0x80070600` | HUD animation/build | animation, scratch/static, OT | medium-high |
| 14 | `0x80050368` | frame audio/static state | audio/static | medium |
| 15 | `0x8009331C` | GPU submission start | GPU and PsyQ static cache | high |

`0x80050368` then occurs twice more before the next overlay entry, from callsite `0x800527F4`. These events belong to the base-loop audio/service work between integrated frames and are retained in each frame group.

The trace sorts by captured CPU cycle and uses each `0x80114780` hit as an active-frame delimiter. Caller is the MIPS callsite estimate `RA-8`. Depth is deliberately only a selected-boundary estimate; this is not a full stack unwind.

## Boundary decisions

| Requested boundary | Result | Evidence |
|---|---|---|
| Logic end | **PARTIAL** after vehicle dispatcher | player/AI update ends at selected seq. 5, but timer and HUD work already occurred and later animation/effect functions are stateful |
| Camera state complete | **DYNAMIC_CONFIRMED** by seq. 8 | camera update at seq. 6 followed by view-matrix construction at seq. 8 |
| Render-state build start | **NOT CONTIGUOUS** | HUD/OT construction starts at seq. 3 before vehicle physics; later render state resumes after camera |
| Geometry transformation start | **DYNAMIC_CONFIRMED candidate** at seq. 10 | selected geometry/OT phase follows camera matrices, but semantics remain medium confidence |
| Ordering-table build start | **DYNAMIC_CONFIRMED** no later than seq. 3 | HUD routines append primitives before vehicle update |
| GPU submission start | **DYNAMIC_CONFIRMED** at `0x8009331C` | occurs after overlay return at base-loop callsite `0x8001EC68` |

There is no single `logic -> camera -> render -> submit` suffix. OT construction begins before player/AI physics, then stateful animation, RNG/audio-capable world effects, geometry, HUD animation, and audio/static updates are interleaved. Re-running the whole overlay or the apparent geometry suffix would repeat non-render side effects.

## Side-effect exclusion

Only dynamically reached selected functions were classified. The classifier rejects a render-only candidate if static evidence includes timer, player, AI, RNG, audio, animation, replay, frame-counter, CD, heap, or general persistent static writes. Scratch/OT-only functions are not automatically authorized; they merely survive this first exclusion.

- Immediately excluded: full overlay, timer, vehicle dispatcher, camera/static matrix path, world animation, world geometry/effects, track/static lookup, HUD animation, frame audio state, and GPU static-cache setup.
- Not excluded by this coarse test: the two isolated HUD primitive builders. They cannot render the 3D scene and therefore are not a 60 fps boundary.
- Unresolved and not authorized: `0x8002E808` and `0x8006EBB4`; both need narrower producer/side-effect evidence before any reuse claim.

No bounded evidence shows heap allocation or CD access in the selected functions. Replay writes were not identified in this runtime path. These are **not observed**, not proof of global absence.

## Classification

Current render-boundary classification: **no proven render-only re-entry point**. The evidence is compatible with later interpolation or an emulator-side presentation approach, but not with simply calling an existing suffix twice.

## Reproduction

```bash
r4-autolab trace-race-call-order \
  --frames 30 --max-events-per-frame 2048 \
  --scenario accelerate-straight-600
```

PASS evidence: ignored `runs/race-call-order/20260716T201317094186Z/call-order.json`, 30/30 frames, 15 bounded breakpoints, 544 events, no failures, zero R4 writes, and no residual PCSX process.
