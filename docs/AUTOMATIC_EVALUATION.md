# Automatic evaluation

Phase 5 compares baseline and candidate JSONL traces by VBlank rather than relying on screenshots alone.

Implemented checks:

- game-timer ratio;
- maximum per-VBlank position, speed, and RPM divergence;
- GPU-state update cadence and duplicate ratio;
- crash, freeze, and dropped-event stability flags;
- raw screenshot dimensions, byte count, SHA-256, black-pixel ratio, and extreme-pixel ratio for 16/24-bpp captures.

Thresholds remain external in `config/success_criteria.example.toml`. `compare` emits both the legacy summary difference and the threshold evaluation:

```bash
r4-autolab compare BASELINE_ID CANDIDATE_ID --criteria config/success_criteria.example.toml
r4-autolab visual-check --raw screenshot.raw --metadata screenshot.json
```

The fake render-only candidate measured approximately 30.25 state changes/s for the baseline and 60.0 changes/s for the candidate, with game-speed ratio 1.0 and zero position/speed/RPM divergence. This validates the evaluator only; it is not R4 evidence.

Known limits: AI cars, gear, steering, drift, collision, lap logic, and replay compatibility require configured telemetry that is not available in the current real capability trace. A valid image size and low black ratio do not establish correct rendering.
