# R4 engine-speed / RPM investigation

## Conclusion

`0x800F4A50` is a **DYNAMIC_CONFIRMED engine-speed-related value**, but its unit and exact RPM scale remain unproven. It must not yet be labelled a calibrated RPM field.

The address was selected from the actual HUD path, not a RAM scan: the race overlay passes it to `FUN_8002169C`, which builds a rotating four-point gauge primitive. The same value is passed to `FUN_80050368`, a frame audio/static-state setter. This links the candidate to both the tachometer-like HUD and engine audio state.

## Dynamic evidence

Across five 120-VBlank scenarios:

- bounded writers: `0x80024664`, `0x800246F0`;
- bounded readers: `0x800245E8`, `0x8002467C`, overlay `0x80114CC8`, overlay `0x80114ED4`;
- the four base PCs are inside `FUN_80023924` (file offset `0x14124`), a player vehicle-update function;
- one write occurs on essentially every active 30 Hz frame;
- HUD/audio reads occur in the same integrated-frame path.

Observed ranges:

| Input | Engine candidate range | Speed-related `object+0x1D8` | Gear candidate `object+0x27A` |
|---|---:|---:|---|
| neutral/coast | 2,161–4,008 | 258–672 | 1–3 |
| accelerate | 3,702–6,687 | 558–690 | 2–3 |
| left/no throttle | 1,216–4,008 | 171–672 | 1–3 |
| right/no throttle | 528–4,008 | 70–672 | 1–3 |
| accelerate + left | 3,461–6,423 | 252–672 | 1–3 |

The candidate tracks speed closely while coasting (`r≈0.97`) but not under all throttle/steering cases (`r≈0.36` and `r≈-0.11` in two scenarios), which is consistent with an engine/gear quantity rather than a duplicate speed field. It is not enough to derive a physical RPM conversion.

## Bounded player-object profile

The only field search read the evidence-backed player object `0x800ABCE0` and stopped at exactly `0x400` bytes, every two VBlanks. It ranked aligned 16/32-bit fields against the known speed-related field. Expected aliases such as `+0x1D8/+0x1DA` and velocity-like `+0x30` ranked highly; no object-local field had stronger HUD/audio provenance than `0x800F4A50`.

No whole-RAM scan, large dump, value write, or guessed RPM patch was used. The raw 0x400-byte snapshots were analyzed in memory and omitted from the JSON report; only bounded rankings and explicit samples were retained.

## Status

- Engine-speed relationship: **DYNAMIC_CONFIRMED**.
- HUD gauge input: **DYNAMIC_CONFIRMED**.
- Audio/static-state input: **DYNAMIC_CONFIRMED** at call level.
- Exact RPM unit, redline, and conversion: **UNKNOWN**.
- Brake scalar and engine pitch register: **UNKNOWN**.

Evidence: ignored `runs/input-engine/20260716T201957810750Z/input-engine.json` and Ghidra exports keyed by `0x800F4A50` / `FUN_80023924`.
