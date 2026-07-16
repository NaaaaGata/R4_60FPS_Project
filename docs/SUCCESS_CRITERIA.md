# Success criteria

The deterministic fake path succeeds when all tests pass, state history is complete, telemetry and artifacts are linked to a run ID, original bytes are restored, and comparison shows the injected render-only change without physics/timer divergence.

A real 60 fps candidate additionally requires at least 58 distinct rendered states per second, duplicate rate below the configured threshold, real/game timer ratio within bounds, matching player/AI physics under identical input, valid countdown/lap behavior, no visual or memory corruption, recorded CPU overclock, multiple courses/views, and an explicit replay-compatibility result. Screenshots alone cannot satisfy these criteria.

Thresholds are configuration, not conclusions; see `config/success_criteria.example.toml`.

