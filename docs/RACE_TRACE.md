# First deterministic R4 race trace

The first real race trace loaded the validated private state, applied the deterministic `CROSS` Pad override, and collected exactly 600 VBlank events over 9.9717 emulated seconds. It then reloaded the state for each bounded breakpoint phase in the required order. Every breakpoint had a 32-hit ceiling, every phase ran 120 VBlanks, all breakpoints/input overrides were cleared, and no PCSX-Redux process remained. No memory write or patch was performed.

## Candidate results

| Candidate | 600-VBlank changes | Approx. update rate | Write hits | Read hits | Conclusion |
|---|---:|---:|---:|---:|---|
| `0x800AC064` frame | 0 | 0 Hz | 0 | not run | Not valid in this race/build evidence |
| `0x800AC0D0/D4/D8` player XYZ | 0 | 0 Hz | 0 | 0 | Not valid in this race/build evidence |
| `0x800AC104` heading | 0 | 0 Hz | 0 | not run | Not valid in this race/build evidence |
| `0x800AC288` speed | 0 | 0 Hz | 0 | not run | Not valid in this race/build evidence |
| `0x800AC32C` RPM | 0 | 0 Hz | 0 | not run | Not valid in this race/build evidence |
| `0x801FFF58` camera claim | 299 | 29.985 Hz | 32 capped | 32 capped | Dynamic, but semantics rejected pending mapping |

The visible HUD and moving car contradict the all-zero vehicle/speed/RPM fields, so the public addresses are not promoted to Japanese-version facts. They are not write targets.

`0x801FFF58` is only 0x38 bytes below the captured stack pointer `0x801FFF90`. Its bounded events came from many unrelated PCs. Frequent sources included writes at `0x80050194` and `0x80084C28`, and reads at `0x800501B0` and `0x80084D2C`; many one-off sources also appeared. This access diversity and stack proximity are stronger evidence for a reused stack location than a stable global camera coordinate. Its roughly 30 Hz cadence is real, but its camera label is not.

Breakpoint events include phase, scenario, state/input SHA-256, VBlank, CPU cycle, PC, RA, SP, GPR, address, width, and cause. The installed PCSX callback does not expose old/new values, so both remain explicit nulls with a limitation string; post-phase memory is recorded separately and is not misattributed to individual hits.

Next discovery should use static mapping of the captured in-payload PCs and bounded observation of actual state structures reached from race update/render functions. It must not scan or dump large RAM ranges and must not patch the disproven public candidates.
