# R4 audio cadence

Scope: read-only Exec cadence from the verified race state. No SPU RAM, game RAM, disc, BIOS, or audio setting was written.

## Top-level cadence

`FUN_8005006C` is called by the base loop at RA `0x8001EC04`, before the race overlay. It and each major sub-update below ran exactly 60 times over 120 VBlanks, on the 60 active integrated frames:

- `FUN_800537C4` — CD/XA state machine;
- `FUN_80054010` — audio parameter/state update;
- `FUN_8004FFA0`, `FUN_80052834` — voice/channel management;
- `FUN_800511B0`, `FUN_80051664`, `FUN_80051840`, `FUN_8004F704`, `FUN_80051BCC` — active voice/effect groups.

`FUN_800504A8` ran 180 times on those 60 active VBlanks (three active channels per frame). `FUN_80050368`, which receives the engine-speed candidate from the overlay and channel values from `FUN_8005274C`, ran 180 times total: 60 overlay calls plus 120 channel calls.

## Lower-level evidence

Bounded lower-level traces show:

| Function | Static role candidate | 120-VBlank result |
|---|---|---:|
| `0x80050168` | SPU voice volume/parameter setter | hit cap 512 on 47 VBlanks; exact count censored |
| `0x80084C10` | SPU voice parameter setter | hit cap 512 on 52 VBlanks; exact count censored |
| `0x80085540` | voice command/setup | 11 hits on 8 VBlanks |
| `0x8008BE74` | CD command/status service | 60 hits / 60 active VBlanks |
| `0x8008BD50` | CD status/result service | 60 / 60 |
| `0x8008C018` | CD control service | 60 / 60 |

The capped SPU setters establish heavy voice-parameter work inside active audio updates but do not establish a precise call rate. `FUN_800537C4` includes XA repeat/state transitions and CD service calls, while the lower CD calls still occur only on active 30 Hz frames in this state.

## Decision

Audio game-side control is coupled to the integrated 30 Hz loop. This does not mean the SPU waveform itself is 30 Hz—the hardware synthesizer runs independently—but volume, pitch/engine inputs, voice management, and XA/CD control are updated from the 30 Hz game path.

Any design that re-runs the whole loop or stateful geometry/effect suffix at 60 Hz risks doubling audio commands. Audio functions are excluded from a render-only re-entry path. No claim is made that audio should or can be changed to 60 Hz.

Evidence:

- ignored `runs/function-trace/20260716T202848242387Z/function-trace.json`;
- ignored `runs/function-trace/20260716T203005322153Z/function-trace.json`;
- Ghidra export of `FUN_8005006C` and its dynamically reached subfunctions.
