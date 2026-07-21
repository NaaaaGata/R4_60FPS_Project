# R4 deterministic AI trajectories

## Validation boundary

The runtime active count at `0x800AC384` is 8. Before sampling, every attempt required:

- count in 2..16;
- exactly count pointers from `0x800FFA00`;
- verified player `0x800ABCE0` first;
- all pointers unique and 4-byte aligned;
- each fixed field window ending at object `+0x2AC` inside 2 MiB PS1 RAM.

The resulting objects are:

| Index | Kind | Pointer | Rank |
|---:|---|---:|---:|
| 0 | player | `0x800ABCE0` | 7 |
| 1 | AI | `0x80106F78` | 0 |
| 2 | AI | `0x80107298` | 1 |
| 3 | AI | `0x801075B8` | 2 |
| 4 | AI | `0x801078D8` | 3 |
| 5 | AI | `0x80107BF8` | 4 |
| 6 | AI | `0x80107F18` | 5 |
| 7 | AI | `0x80108238` | 6 |

## Three-run result

Three fresh PCSX-Redux processes loaded the same state and ran `accelerate-straight-600`. Each produced 300 samples at two-VBlank intervals and exactly 300 hits at shared dispatcher `FUN_80038338`. All pointers, X/Y/Z, three orientation components, speed-related field, rank, and course-progress pairs matched sample-for-sample across all three attempts.

Classification: **DYNAMIC_CONFIRMED deterministic player/AI trajectories** for this state/input.

## Per-vehicle changes over 299 sample transitions

| Index | X | Y | Z | orientation Y | speed-related | progress B |
|---:|---:|---:|---:|---:|---:|---:|
| player | 299 | 155 | 299 | 10 | 267 | 299 |
| AI 1 | 295 | 159 | 299 | 225 | 105 | 299 |
| AI 2 | 290 | 91 | 299 | 210 | 0 | 299 |
| AI 3 | 299 | 159 | 299 | 275 | 0 | 299 |
| AI 4 | 298 | 284 | 299 | 280 | 32 | 299 |
| AI 5 | 299 | 297 | 299 | 285 | 58 | 299 |
| AI 6 | 299 | 262 | 299 | 279 | 61 | 299 |
| AI 7 | 299 | 182 | 299 | 212 | 74 | 299 |

Field changes are value-dependent; a constant speed-related field for two AI cars does not mean their dispatcher stopped. Their X/Z/progress and orientation trajectories advance while the shared dispatcher hits once per active 30 Hz frame.

## Consequence for rendering

AI cannot be ignored by a player-only 60 Hz visual approach. Seven independently moving AI objects share the same 30 Hz dispatcher and would remain visually stepped unless all visible vehicle transforms are shadowed/interpolated or presentation is handled after game rendering. This is a design constraint, not authorization to add interpolation code.

## Reproduction

```bash
r4-autolab trace-ai-trajectories \
  --scenario accelerate-straight-600 \
  --attempts 3 --vblanks 600 --sample-every 2
```

PASS evidence: ignored `runs/ai-trajectories/20260716T202434661932Z/ai-trajectories.json`; 900 samples total, 900 dispatcher hits, exact three-run signatures, zero R4 writes, normal process cleanup.
