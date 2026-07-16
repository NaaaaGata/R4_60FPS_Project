# R4 game-side input path

Scope: five official PCSX Pad-override scenarios, each reloaded from the verified state and sampled for 120 VBlanks. The analysis uses six bounded breakpoints and a fixed player object; it performs no R4 memory writes.

## Confirmed game bitfield

`0x800F3820` is the game-side controller-1 bitfield used by the race overlay and multiple base functions. The low and high halfwords have edge/current behavior:

| Scenario | Stable/current high-half mask | Initial low-half evidence |
|---|---:|---:|
| neutral | `0x0000` | `0x0000` |
| CROSS | `0x0040` | not captured at the 2-VBlank sample boundary |
| LEFT | `0x8000` | `0x8000` on initial transition |
| RIGHT | `0x2000` | `0x2000` on initial transition |
| CROSS + LEFT | `0x8040` | `0x8000` on initial transition |

The 32-bit examples are `0x00400000`, `0x80000000`, `0x20000000`, and `0x80400000`; initial edge/current combinations include `0x80008000` and `0x20002000`. This is an active-high normalized game bitfield, not the original serial pad packet. Analog steering values were not observed because the configured controller override scenarios are digital.

## Producer and consumers

Ghidra xrefs and bounded Write events agree:

- `FUN_8004AA7C` (file offset `0x3B27C`) is the base frame-post/input-normalization function.
- `0x8004AD40` writes the low halfword at `0x800F3820`.
- `0x8004B6C4` writes the current/held halfword at `0x800F3822`.
- The function is called at base-loop RA `0x8001ECB0`, once per active 30 Hz frame.

Bounded Exec cadence was 60 calls over each 120-VBlank scenario for frame post, next race overlay entry, and vehicle dispatcher. The normalized bitfield is therefore produced after one integrated frame and consumed by the next overlay/vehicle update.

Static consumers include the race overlay, `FUN_8007346C` world/animation state, `FUN_80045C24`, `FUN_800559A0`, and controller/HUD function `FUN_800223F0`; additional reads exist and are not exhaustively relabelled. The player-response path is:

```text
PCSX Pad override
  -> game pad/SIO service (raw packet not directly captured)
  -> FUN_8004AA7C normalization
  -> 0x800F3820 edge + 0x800F3822 held masks
  -> next race overlay / vehicle dispatcher and selected consumers
  -> player object physics fields
```

The exact lower-level SIO packet parser and a continuous steering/throttle/brake scalar are **UNKNOWN**. CROSS, LEFT, and RIGHT digital masks and their 30 Hz game-side normalization are **DYNAMIC_CONFIRMED**.

PASS evidence: ignored `runs/input-engine/20260716T201957810750Z/input-engine.json`, five scenarios × 60 samples, deterministic state/input identities, zero R4 writes, normal cleanup.
