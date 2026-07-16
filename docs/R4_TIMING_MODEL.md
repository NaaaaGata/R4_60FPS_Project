# R4 Japanese race timing model

This model applies only to the verified `SLPS-01800` executable SHA-256 `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775` and the captured private race state. It combines deterministic runtime evidence with bounded Ghidra output. No memory write or patch was used.

## Confirmed cadence

| Subsystem/evidence | Runtime identity | Result over VBlank | Confidence |
|---|---|---:|---|
| VBlank | PCSX `GPU::Vsync` | 600 events / 9.96 s | confirmed |
| Race overlay entry | `0x80114780` | 300 / 600 | confirmed 30 Hz |
| Main-loop landmarks | `0x8001EB88`, `0x8001EC30`, `0x8001EC5C` | 300 / 600 each | confirmed 30 Hz |
| Vehicle/AI dispatcher | `FUN_80038338` | 300 / 600 | confirmed 30 Hz |
| Vehicle update phases | `FUN_80029908`, `FUN_80022EC8` | 60 / 120 each | confirmed 30 Hz for this race path |
| Camera transform update | `FUN_80034178` | 300 / 600 | confirmed 30 Hz |
| Lap/timer logic | `FUN_8003C838` | 60 / 120 | confirmed 30 Hz |
| Frame post-processing | `FUN_8004AA7C` | 300 / 600 | confirmed 30 Hz |
| Raw displayed image | `PCSX.GPU.takeScreenShot()` SHA-256 | 60 changes / 120 intervals | confirmed 29.97 Hz |
| GPU submit A | `FUN_8009331C` | 60 / 120 | confirmed 30 Hz |
| GPU submit B | `FUN_80093150` | 60 / 120 | confirmed 30 Hz |
| GPU submit C | `FUN_800930E0` | 120 calls on 60 / 120 VBlanks | confirmed two calls per 30 Hz frame |

The screenshot sequence contains one initial sample followed by runs of exactly two equal hashes. It therefore shows real duplicate display states on alternating 60 Hz VBlanks, not merely an emulator FPS counter. The fallback is weaker than a GPU command-stream hash, but the exact AABB-style sequence agrees with every dynamically traced race subsystem.

## Function evidence table

| Role | RAM range | File offset | Dynamic caller / cadence | Static inputs and outputs | Confidence |
|---|---|---:|---|---|---|
| Race main loop | `0x8001EB04–0x8001ECC3` | `0xF304` | landmarks `+0x84/+0x12C/+0x158`: 300/600 | parity global and mode callback in; GPU submissions/counter out | high |
| Active race overlay | base `0x801146F0`, entry `0x80114780` | overlay `0x90` | indirect `jalr v0` at `0x8001EC30`: 300/600 | race globals/player table in; update/render/HUD calls out | high |
| Vehicle/AI dispatcher | `0x80038338–0x800389B3` | `0x28B38` | overlay RA `0x80114D70`: 300/600 | pointer table `0x800FFA00`, active count in; all car state out | high |
| Vehicle phase A | `0x80029908–0x8002A07F` | `0x1A108` | RA `0x800383D8`: 60/120 | car object/index in; position/physics state out | medium-high |
| Vehicle phase B | `0x80022EC8–0x80022FF3` | `0x136C8` | RA `0x800383E4`: 60/120 | car object/index in; secondary vehicle state out | medium-high |
| Camera transform | `0x80034178–0x800344CF` | `0x24978` | overlay RA `0x80114DB0`: 300/600 | object `+0x10..18`, `+0x50..58` in; scratch transform state out | high |
| Lap/timer logic | `0x8003C838–0x8003CF2B` | `0x2D038` | overlay RA `0x80114C4C`: 60/120 | lap `+0x2AA`, progress `+0x184/+0x188` in; lap counters/results out | high |
| Frame post-process | `0x8004AA7C–0x8004BA3F` | `0x3B27C` | main RA `0x8001ECB0`: 300/600 | global frame/race state in; per-frame state out | medium-high |
| VSync service | `0x8008AEF0–0x8008B067` | `0x7B6F0` | statically called by main loop polling | VBlank mode in; counter/timing result out | medium-high |
| GPU submit A/B/C | `0x8009331C–0x80093813`, `0x80093150–0x8009320F`, `0x800930E0–0x8009314F` | `0x83B1C`, `0x83950`, `0x838E0` | main RAs `0x8001EC70/7C/88/A8`; 30 Hz frames | display-list/environment pointers in; GPU work out | high cadence, medium semantics |

Representative pseudocode, simplified from Ghidra and checked against dynamic calls:

```text
loop forever:
    choose frame/buffer parity
    invoke active mode callback (race overlay)
    poll VSync and obtain timing
    submit GPU environment/list work (A, B, C, C)
    run frame post-processing
    increment frame state

race overlay frame:
    update race/lap state
    dispatch every active vehicle through physics/AI phases
    update player camera transform
    build HUD/render state
```

## Verified state structure

The race overlay reads player pointer `0x800FFA00 = 0x800ABCE0`. Ghidra and bounded writes identify these fields:

| Address / offset | Interpretation | Dynamic result |
|---|---|---|
| `0x800ABCF0` / `+0x10` | X position | 299 changes / 600, 30.013 Hz |
| `0x800ABCF4` / `+0x14` | Y position | 155 changes / 600; terrain-dependent |
| `0x800ABCF8` / `+0x18` | Z position | 299 changes / 600, 30.013 Hz |
| `0x800ABD30/34/38` / `+0x50/54/58` | orientation components | value-dependent changes; bounded writers confirmed |
| `0x800ABEB8` / `+0x1D8` | speed-related field | 267 changes / 600, 26.80 Hz |
| `0x800ABECE` / `+0x1EE` | rank index | constant `7` (HUD displays 8th), writer confirmed |
| `0x800ABF8A` / `+0x2AA` | lap index | constant `1` during sample |
| `0x800ABE64/68` / `+0x184/+0x188` | course progress pair | second component written every race update |

`FUN_80038338` iterates the pointer table at `0x800FFA00` up to the active-car count and runs the update phases. This is evidence that player and AI vehicle processing share the same 30 Hz dispatcher, although per-AI trajectory equivalence has not yet been measured.

## Main-loop relationship

The static and dynamic evidence supports this sequence:

```text
60 Hz GPU::Vsync
    -> every second VBlank: base main-loop iteration
       -> indirect race overlay entry 0x80114780
          -> vehicle/player/AI dispatcher
          -> lap/timer logic
          -> camera update
          -> render/HUD command construction
       -> GPU submission / buffer work
       -> frame post-processing
    -> displayed raw image repeats for the intervening VBlank
```

The base loop polls VSync and switches parity/buffer state, but the active race overlay, physics/AI dispatcher, camera, timer logic, and displayed pixels all advance at 30 Hz. There is not yet evidence for an independent 60 Hz render path with 30 Hz physics.

Classification: **E — integrated 30 Hz loop**. This is stronger than category B because GPU submission and displayed-image changes have now been correlated to the same 30 Hz iteration; it is not category C because no separable render-only invocation has been observed.

## Exact wait branch and parity

The previous cadence conclusion is now backed by branch-level evidence. `0x8001EC48` calls `FUN_8008AEF0` with `a0=1`; `0x8001EC50` compares its return with the state-specific threshold `s0=384`; and `bne` at `0x8001EC54` returns to the poll while the comparison is true. Its `0x8001EC58` delay slot is `nop`. The not-taken path reaches `0x8001EC5C`, which calls the same service with `a0=0` in its delay slot. The bounded trace observed 2,397 taken and three not-taken outcomes before its 2,400-event branch cap.

Over a separate 600-VBlank run, active and duplicate intervals alternated exactly 300/300. Every fixed race watch and screenshot hash stayed unchanged on duplicate intervals. Active frames alternated parity 0/1 and command bases `0x800AD8D0` / `0x800D0048`, separated by `0x22778`. Full branch metadata, delay-slot handling, and bounds are in `docs/R4_LOOP_PARITY.md`.

A 240-VBlank GPU trace decoded opposing 320×240 display/draw pages at VRAM Y=0 and Y=240. It bounded-traversed both submitted ordering tables on all 120 active frames: the primary content hash changed on every active frame, the secondary list was stable, and duplicates made no submission and reused the prior command/screenshot hashes. See `docs/R4_GPU_PIPELINE.md`.

Three independent 600-VBlank AI runs validated eight unique vehicle objects and produced identical 300-sample trajectories. The shared `FUN_80038338` dispatcher hit exactly 300 times per run, while every AI changed X/Z/progress on nearly every active sample. This confirms individual AI motion is part of the same 30 Hz update, not merely a dispatcher inference.

## Consequence for experiments

A safe 60 fps candidate cannot be inferred by simply removing a wait or doubling the whole loop: the measured loop contains physics, AI, camera, timer, HUD, and rendering together. Such a change has a high risk of doubling game speed and invalidating lap timing. The next patch candidate must first isolate a render-only call path or introduce interpolation with explicit evidence. Until then, patch generation remains gated off.

Known limits: GPU command content hash and display/draw-buffer identity remain unverified; the exact wait/parity branch is now mapped, but the input-read function, replay path, and RPM field have not been mapped; AI vehicle trajectories, other courses/views, replay compatibility, audio cadence, and overclock requirements remain unverified. These are recorded as unresolved rather than inferred.
