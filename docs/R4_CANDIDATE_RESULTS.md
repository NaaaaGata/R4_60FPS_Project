# Evidence-gated R4 candidate results

## Gate outcome

No 60 fps RAM patch candidate is authorized for the verified Japanese build. Dynamic traces and Ghidra correlate the active race overlay, vehicle/AI dispatcher, camera, lap timer, frame post-processing, and raw displayed image at 30 Hz. No independently callable render-only branch, buffer-swap gate, or interpolation path has been identified.

Changing the integrated loop cadence would risk doubling physics, AI, timer, camera, HUD, and audio behavior. The project therefore did not create a guessed patch from constants such as 2, 30, or 60 and did not write any R4 address.

## Candidate/evaluation accounting

| Item | Result |
|---|---|
| Evidence-backed patch candidates | 0 |
| R4 RAM experiments | 0 |
| Successful 60 fps candidates | 0 |
| Failed R4 patch candidates | 0 (none were safe enough to execute) |
| Baseline displayed-image cadence | 29.97 Hz |
| Baseline duplicate transition ratio | 0.50, exact two-VBlank runs |
| Candidate game-speed ratio | not applicable; no candidate ran |
| R4 patch restoration | not exercised because no R4 patch was authorized |
| Non-code scratch restoration | PASS; separate bridge capability proof only |

The published address hypotheses were disproven as Japanese-build state fields; they are rejected observation leads, not failed patch experiments.

## Real Codex gate

A single real Codex proposal campaign used a code-signed Codex CLI 0.144.5 with an ephemeral read-only sandbox, web search disabled, strict JSON Schema output, one call, one proposal, 300-second maximum, one-change maximum, and non-zero finite accounting budget. The reviewed evidence catalog intentionally contained zero changes.

Codex returned `changes=[]` and the hypothesis that no evidence-backed render-only RAM change exists. The Supervisor-side proposal gate classified it `NO_SAFE_CHANGE`; emulator experiments remained zero. Two earlier calls failed on strict Structured Outputs schema compatibility and are retained as FAILED campaign records; neither reached an emulator.

The next safe work is additional observation/static correlation of GPU submission, display/draw buffers, render-skip branches, replay handling, and RPM—not patch execution.

## Render-boundary follow-up gate

The exact main-loop wait branch is now identified at `0x8001EC54`, including its `nop` delay slot and fall-through to the `VSync(0)` call at `0x8001EC5C`. A 600-VBlank read-only trace produced an exact 300 active / 300 duplicate alternation. Frame state, player state, command-base selection, GPU submission, and displayed pixels all remain unchanged on each duplicate interval.

This strengthens the no-patch decision: the observed gate surrounds the integrated update/render iteration, not a proven render-only call. Its removal or inversion is therefore not an evidence-backed candidate. Candidate count and R4 RAM experiment count remain zero.
