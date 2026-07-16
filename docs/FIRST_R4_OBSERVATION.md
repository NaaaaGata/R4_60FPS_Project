# First R4 observation

This Phase 7 run is a read-only boot/title-flow observation. It is not a race baseline and is not evidence for a 60 fps patch.

## Confirmed target identity

- Disc ID reported by PCSX-Redux: `SLPS01800`
- Boot path from `SYSTEM.CNF`: `SLPS_018.00;1`
- Normalized serial: `SLPS-01800`
- Extracted executable SHA-256: `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775`
- Executable size: 641,024 bytes
- PS-X EXE payload size: 638,976 bytes
- Load address: `0x80010000`
- Initial PC: `0x8007D4B4`
- Global pointer header value: `0x00000000`

Extraction was read-only from the owned MODE2/2352 BIN/CUE into ignored `private/extracted/`. The original image was not changed.

## Observation configuration

- PCSX-Redux build: `4ad775e47d47cc9023aa45a2f439289c5897801a`
- Bundled OpenBIOS, interpreter, debugger
- 600 VBlank (~10 seconds)
- Eight public-analysis candidate addresses sampled as 32-bit values
- Read and Write breakpoints, each limited to 16 hits
- No input replay, save state, memory write, or patch
- Local report: `runs/observations/r4-boot-20260716T165118086434Z/observation.json`

## Observed facts

- `0x800AC064`, player XYZ, heading, speed, and RPM candidates remained zero in all 600 periodic samples.
- Those addresses received boot/initialization writes through `0x8007D4C4` and KSEG1 aliases, but no runtime reads were captured in this window.
- `0x801FFF58` changed four times (~0.40 changes/s) and produced runtime reads and writes.
- Example `0x801FFF58` writers: `0x80083A74`, `0x80083AD8`, `0x8008B13C`, `0x8008C158`, `0x8008CA20`, `0x8008CA38`, `0x8008CA40`, `0x8008CF78`, `0x8008CF80`, `0x8008CF98`.
- Example readers: `0x800825BC`, `0x80083B64`, `0x8008B150`, `0x8008C284`, `0x8008CC70`, `0x8008CC78`, `0x8008CC80`, `0x8008D34C`, `0x8008D354`, `0x8008D35C`.
- Breakpoint IDs were corrected to use a monotonic counter after the first run exposed duplicate `bp-1` identifiers.

## Interpretation

- The camera candidate has confirmed runtime activity during boot/title flow, but its semantic role is still unverified.
- The absence of vehicle/frame activity is expected outside a loaded race and does not reject those address hypotheses.
- Writes through `0x8007D4C4` appear consistent with executable initialization, but this remains an inference until static analysis is available.

## Blockers to race investigation

- No deterministic race save state in the explicitly supported `.rawstate` format.
- No deterministic input script or verified menu-navigation automation.
- Ghidra Headless is not installed, so captured PCs cannot yet be mapped to functions/xrefs reproducibly.

Resume only after a race state and input are prepared privately. The next run should capture `0x800AC064` and vehicle-coordinate Write PCs first, then bounded Read PCs, and correlate them with VBlank. It must still remain observation-only.
