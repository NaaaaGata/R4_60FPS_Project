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

The screenshot sequence contains one initial sample followed by runs of exactly two equal hashes. It therefore shows real duplicate display states on alternating 60 Hz VBlanks, not merely an emulator FPS counter. The fallback is weaker than a GPU command-stream hash, but the exact AABB-style sequence agrees with every dynamically traced race subsystem.

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

## Consequence for experiments

A safe 60 fps candidate cannot be inferred by simply removing a wait or doubling the whole loop: the measured loop contains physics, AI, camera, timer, HUD, and rendering together. Such a change has a high risk of doubling game speed and invalidating lap timing. The next patch candidate must first isolate a render-only call path or introduce interpolation with explicit evidence. Until then, patch generation remains gated off.

Known limits: GPU command count/hash and display-buffer identity are unavailable through a confirmed Lua API; RPM has not been mapped; AI vehicle trajectories, replay compatibility, other courses/views, and overclock requirements remain unverified.
