# R4 interpolation feasibility

## Final result: RESULT_C

The current evidence does not provide a safe render-only re-entry point or a safe game-side interpolation insertion point. The integrated overlay interleaves timer/HUD, player and AI physics, camera, stateful animation, geometry/effects, audio/static updates, and ordering-table construction. Existing `render_x/y/z` fields are same-frame copies, not retained previous state. Therefore no patch or RAM experiment is authorized.

This is not a claim that interpolation is impossible in principle. It means the required state ownership and side-effect-free render boundary are absent or unproven in the current scene.

## Existing state assessment

The 120-VBlank state-pair trace sampled player and first AI on every VBlank:

- current XYZ `+0x10/+0x14/+0x18` and render copy `+0xC8/+0xCC/+0xD0` matched on all 60 active samples;
- render copy did not match previous active X/Z for player or AI;
- `+0x20/+0x24/+0x28` is approximately quarter-scale source position, not previous position;
- orientation `+0x80/+0x82/+0x84` is a current/reconstructed orientation copy, not a proven prior orientation;
- camera scratch XYZ changed on 60 active frames and stayed unchanged on duplicates;
- no interpolation fraction or 60 Hz smoothing accumulator was identified;
- replay transform function `FUN_8002ECD0` was not reached and remains STATIC_ONLY.

## Design comparison — no implementation

### A. Re-run an existing render function on duplicate VBlank

Result: **rejected**.

The full overlay repeats physics, AI, timer, input consumption, RNG/audio-capable animation, HUD, and OT writes. The post-camera suffix still contains stateful world/effect and audio work. Display/draw pages and command arenas are understood, but preparing the next page requires rebuilding commands under correct GPU synchronization. No verified code cave or side-effect-free call signature exists; none was created.

### B. Interpolate only player and camera

Result: **visually incomplete**.

Seven AI cars have deterministic independent 30 Hz trajectories. Player/camera interpolation would leave AI, wheels, shadows, effects, and some track-relative objects stepped. HUD timing could stay 30 Hz, but mismatched camera versus AI geometry would produce relative jitter. Collision remains untouched, which is desirable, but replay and respawn discontinuities are unresolved.

### C. Interpolate all vehicles and camera

Result: **most coherent game-side concept, currently blocked**.

A future design would need external shadow state rather than overwriting physics state:

```text
per 30 Hz active update:
    previous <- current shadow
    current  <- post-dispatch transforms for 8 validated vehicles + camera

per intervening presentation:
    alpha = 0.5
    build temporary render transforms with fixed-point lerp
    use shortest-arc wrapped orientation interpolation
    render into the opposite draw page with a fresh bounded command arena
    restore every temporary value before any logic/audio/timer work
```

Minimum conceptual shadow state for eight cars is previous/current XYZ and orientation, plus camera position/target/matrix and discontinuity flags. At six 32-bit components × two snapshots × eight cars, vehicle state alone is 384 bytes before camera/flags/alignment. Exact RAM placement is intentionally unspecified because this phase forbids code injection and no safe unused region is established.

Required guards include 12-bit/angle wrap, fixed-point rounding, teleport/respawn threshold, collision snap, race start/countdown, finish, camera switch, replay mode, object-count changes, and fallback to current state on any discontinuity. The blocker is not storage size; it is the absence of a proven boundary where temporary values can feed all geometry without touching physics/AI/audio/animation or corrupting the double-buffered OT.

### D. Reuse or transform GPU command lists

Result: **rejected for camera-aware interpolation**.

The primary OT contains GTE-produced screen coordinates, depth ordering, clipping, lighting, sprites, and effects. Re-submitting it is exactly the existing duplicate image. Editing screen coordinates cannot correctly reconstruct camera motion, newly visible geometry, depth order, or clipping. Mutating active lists would also threaten DMA/GPU synchronization. The command hashes are useful evidence, not an interpolation substrate.

## Preferred safe research direction

The next practical option is emulator-side presentation interpolation using two completed 30 Hz frames, because it does not mutate game logic, RAM, OT construction, audio, replay, or timing. It would still be presentation interpolation, not “real game render 60 fps,” and must be labelled accordingly. A true game-render solution requires new evidence for a side-effect-free geometry builder or a controlled all-vehicle shadow-render boundary.

## Additional-state plan

No state capture is requested now. If the user later authorizes more observation, use this order:

| State name | Required scene | Reason / fields and functions | Expected evidence | Priority |
|---|---|---|---|---:|
| `corner-pack` | corner with nearby AI | all vehicle XYZ/orientation, camera, OT hashes | angle wrap and relative AI jitter | 1 |
| `camera-switch` | manual camera change | camera scratch/matrices, mode callbacks | discontinuity handling and camera ownership | 1 |
| `respawn` | off-track respawn | transform pairs, teleport flags, dispatcher | snap/fallback threshold | 1 |
| `race-start` | countdown to launch | timer/input/audio/vehicle boundary | initialization of previous/current shadows | 2 |
| `finish-replay` | finish and replay transition | mode table, `FUN_8002ECD0`, replay buffers | runtime replay cadence and transform path | 2 |
| `ai-dense` | multiple cars filling view | eight vehicle transforms and geometry producers | occlusion/depth-order requirements | 2 |
| `collision` | wall/vehicle impact | collision state, camera shake, effects/audio | discontinuity and side-effect isolation | 2 |
| `night-effects` | night/special-effects course | world effects, lighting, primary OT | effect and lighting state requirements | 3 |
| `two-player` | split-screen race | callback table, two cameras, buffers/OT roots | multi-viewport buffer ownership | 3 |

## Gate for any future experiment

Do not proceed to RAM-only interpolation until all of the following are dynamically confirmed: a render-only boundary, complete required inputs, no physics/AI/timer/input/RNG/audio writes, temporary state restoration, fresh command arena ownership, correct display/draw swap, GPU idle/synchronization behavior, replay/respawn fallback, and deterministic rollback on every exception. None of those gates is waived by RESULT_C.
