# R4 replay / demonstration path

## Status

Current status is **STATIC_ONLY**. The captured race state did not transition to replay, and bounded Exec probes recorded zero hits for `FUN_8002ECD0` and `FUN_8002D3B8` over 120 VBlanks. No new state was requested and no mode value was modified.

## Static mode evidence

The base main loop selects a callback through the table rooted at `0x8009E78C`. One table at `0x8009FBAC` contains owned-overlay callbacks including active race `0x80114780` and additional candidates `0x80118C74`, `0x8011487C`, `0x8011493C`, and `0x80115CB4`. The base executable also contains the string `DEMONSTRATION` at `0x800A1DD4`.

These addresses establish alternate race/demo modes, but the exact enumeration remains unnamed. They must not be called “replay mode IDs” without runtime reachability.

## Recorded-transform candidate

An alternate overlay candidate around `FUN_80118C4C` checks a mode byte and calls `FUN_8002ECD0(0x800ABCE0)`. Static decompilation of `FUN_8002ECD0` shows a recorded/playback-style transform reconstruction:

- object `+0x20/+0x24/+0x28`, scaled left by 2, seeds current XYZ `+0x10/+0x14/+0x18`;
- orientation `+0x50/+0x54/+0x58` is copied to 16-bit `+0x80/+0x82/+0x84`;
- transform matrices are rebuilt in `+0x40`, `+0x60`, and `+0x70` regions;
- movement/offset components are added;
- final XYZ is copied to `+0xC8/+0xCC/+0xD0`, with `+0xD4` auxiliary state.

This is evidence for a recorded vehicle transform path and camera/render-state reconstruction. It is not evidence for 60 Hz interpolation. No independently advancing interpolation fraction or second render invocation was identified.

Another overlay function around `0x801148B8` builds HUD/geometry from existing state without invoking the normal vehicle dispatcher. Its mode semantics and safety are uncertain; it may be a paused/alternate presentation state rather than a callable replay renderer. It remains a static boundary candidate only.

## Replay requirements still unknown

- exact replay/demo mode identifier and transition;
- recorded input buffer format and tick cadence;
- whether ghost/demo shares the same object path;
- replay camera mode and buffer ownership;
- whether `FUN_8002ECD0` runs at 30 Hz in an actual replay;
- compatibility of any future shadow/interpolated state.

No replay-specific render path is dynamically confirmed, and no existing 60 Hz interpolation path is proven.
