# R4 race-loop parity and VSync gate

This report is limited to the verified Japanese executable SHA-256 `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775` and state SHA-256 `a80f4a2c1dead74c41e309fe0762b397e635e390ba46ce8251f016b3c595c1e7`. The trace used `accelerate-straight-600`, enforced a read-only PCSX host, and performed zero R4 memory writes.

## Result

The race has an exact alternating active/duplicate VBlank pattern in this state:

| Observation over 600 VBlanks | Count |
|---|---:|
| Active integrated-loop intervals | 300 |
| Duplicate intervals | 300 |
| Screenshot transitions | 299 after the initial hash |
| Main/race/vehicle/camera/timer/post hits | 300 each |
| GPU submit A / B hits | 300 each |
| GPU submit C hits | 600, twice per active interval |

All 599 adjacent classifications alternate. On every duplicate interval, all 16 fixed watches equal the preceding active interval and the screenshot hash is unchanged. This includes frame counter, race tick, player transform, orientation, speed-related field, lap/progress, parity, command base, and the optional-submit flag. The evidence supports a duplicate display VBlank caused by waiting between integrated 30 Hz iterations, not a hidden second render-only invocation.

## Exact gate inventory

Ghidra Headless exported branch target, fall-through, preceding instruction, and delay slot. Runtime Exec breakpoints decoded outcomes from captured GPRs.

```text
0x8001EC48  jal  FUN_8008AEF0       # delay slot sets a0 = 1
0x8001EC50  slt  v0,v0,s0           # VSync(1) result < threshold
0x8001EC54  bne  v0,zero,8001EC48   # continue bounded polling
0x8001EC58  nop                      # branch delay slot
0x8001EC5C  jal  FUN_8008AEF0       # fall-through VSync call
              delay slot sets a0 = 0
```

The saved race state supplies `s0 = [0x800AC3C4] = 384`, not the initialization value seen elsewhere. The bounded runtime sample recorded 2,397 taken and three not-taken outcomes before its 2,400-hit cap. A not-taken outcome reaches `0x8001EC5C`; the subsequent integrated-loop markers occur once every two PCSX `GPU::Vsync` events. `FUN_8008AEF0(1)` is therefore used as a timing poll and `FUN_8008AEF0(0)` as the fall-through VSync service in this path. The semantic unit of 384 remains unlabelled; calling it a scanline or HBlank threshold would require stronger API/source evidence.

The second selected branch is:

```text
0x8001EC94  beq v0,zero,8001ECA8
0x8001EC98  nop
```

It was not taken on all 300 active frames (`v0 = 1`), agreeing with `[0x800AC9E0] = 1` and the second call to GPU submit C.

## Parity and command buffers

The main frame counter rose exactly once per active interval. Its low bit was copied to `0x800F49D0`, and command construction alternated between:

| Frame parity | Command base | Active observations |
|---:|---:|---:|
| 0 | `0x800AD8D0` | 150 |
| 1 | `0x800D0048` | 150 |

The bases differ by `0x22778`, matching the static main-loop stride. Both values remain unchanged on duplicate intervals. This proves double-buffered command-storage selection. It does not yet prove the corresponding displayed VRAM page or the byte-level GPU command-list identity; those are separate bounded tasks.

## Reproduction and bounds

```bash
r4-autolab trace-loop-parity \
  --scenario accelerate-straight-600 \
  --branches config/loop_parity_branches.example.json \
  --vblanks 600 --max-events 20000 --timeout 90
```

Evidence is retained under ignored `runs/loop-parity/20260716T194739777942Z/`. The run produced 6,000 bounded breakpoint events, a 3.9 MiB JSON report, and no residual PCSX process. Breakpoint count was 12, below the hard limit of 16. No broad memory dump, Read/Write breakpoint, scratch test, or patch was used.

## Confidence and limits

- Confirmed: exact active/duplicate alternation for 600 VBlanks in this state and scenario.
- Confirmed: integrated race, vehicle, camera, timer, post, and GPU work occurs only on active intervals.
- Confirmed: frame parity selects two command-storage bases separated by `0x22778`.
- Confirmed: selected MIPS branch outcomes and delay slots are decoded with bounded events.
- Not yet confirmed: display/draw VRAM page identity, GPU linked-list contents, input-read function, audio/replay cadence, or a separable render boundary.
