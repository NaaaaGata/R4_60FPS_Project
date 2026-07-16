# Manual race-state capture

`r4-autolab capture-manual-state --name race-straight` limits ordinary human work to navigating the already-owned game to a stable race moment and pressing Enter once.

Before showing the prompt, the command verifies the CUE's `SYSTEM.CNF`, serial `SLPS-01800`, extracted executable SHA-256, PCSX-Redux IPC handshake, interpreter/debugger availability, and that the sampled PC entered the executable payload. PCSX-Redux is launched with `-run`, `-stdout`, `-lua_stdout`, `-interpreter`, `-debugger`, `-portable`, `-bios`, `-iso`, and `-dofile`; `-testmode` is deliberately absent.

After Enter, the command pauses first, reads registers/counters and the bounded candidate watch set, captures raw pixels and dimensions, creates an explicitly uncompressed raw-protobuf `.rawstate`, hashes the state/CUE/BIN/BIOS, verifies that CUE/BIN hashes did not change, and reloads the state once in the capture process. The default path is `states/manual-race-<UTC timestamp>/`, which is ignored by Git.

Unless `--no-shutdown` is supplied, the capture process is closed and three new test-mode PCSX-Redux processes independently load the state. Each records initial and 60-VBlank PC/RA/SP/GPR, candidate values, counters, screenshot hash, and dimensions under `runs/state-validation/<timestamp>/`. A PASS requires every sample's execution context to be in the verified payload (either PC directly, or the standard PS1 exception vector with RA returning into the payload), identical initial candidate values, identical 60-VBlank candidate trajectories, and identical initial/final raw screenshot hashes. Process failures are FAIL; completed but non-identical evidence is UNKNOWN and retained for investigation.

The command finally updates ignored `config/project.toml` with repository-relative paths where possible. It never writes the disc, BIN, BIOS, extracted executable, or known R4 candidate addresses. `--no-shutdown` intentionally skips fresh-process validation and leaves PCSX-Redux running for debugging.
