# Deterministic PCSX-Redux input

R4 AutoLab uses the official PCSX-Redux Lua Pad API, not OS-level keyboard automation. The bridge targets `PCSX.SIO0.slots[1].pads[1]`, activates named buttons with `setOverride`, and releases them with `clearOverride`. The API and constants are documented in the official [Redux basic API](https://pcsx-redux.consoledev.net/Lua/redux-basics/).

`r4-autolab replay-input` loads the verified raw race state in a fresh PCSX-Redux process for every attempt. Input is set while paused, execution advances in bounded VBlank chunks, and all overrides are cleared in the normal path, Python `finally` cleanup, Lua shutdown dispatch, and the emulator `Quitting` event. Contradictory directions, duplicate/unknown buttons, more than 16 buttons, and scenarios longer than 3,600 VBlanks are rejected.

The public definitions in `config/input_scenarios.example.json` include `neutral-120`, `accelerate-straight-600`, `steer-left-300`, `steer-right-300`, and `accelerate-and-steer-600`. Every definition is canonically serialized and SHA-256 hashed. A default run replays every scenario three times and samples candidate values plus raw screenshot hashes every 60 VBlanks:

```bash
r4-autolab replay-input --attempts 3 --sample-every 60
```

The first real run passed all five scenarios. For each scenario, all three complete screenshot/candidate trajectories matched, the screen changed over time, input-release acknowledgement succeeded, and no PCSX-Redux process remained. The different left/right/fused scenarios produced distinct final screenshots and opposite-signed changes at the camera candidate, providing evidence that the pad override affected the game deterministically. The other published candidate addresses remained zero and are not treated as valid Japanese-version fields.
