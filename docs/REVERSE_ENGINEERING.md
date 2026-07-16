# Reverse-engineering notebook

## Target identity

- Serial: `SLPS-01800` (**confirmed from SYSTEM.CNF and PCSX disc ID**)
- Executable SHA-256: `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775`
- Load address: `0x80010000`
- Initial PC: `0x8007D4B4`
- Observed disc-image SHA-256: `72e54ea4bf6da5a2e839a355e9dcacae989fcddcab84b85cbbb4b2ff08f4a716` (622,452,096-byte user-provided `.bin`; this is **not** the executable hash)
- Observed CUE SHA-256: `139eedfa188f0612f30bca2c0e9fb6d2fdbfd2502a9dc71fceafd73da3011e95` (80-byte user-provided `.cue`)
- PCSX-Redux version/API: changeset `4ad775e47d47cc9023aa45a2f439289c5897801a`, real bridge verified (the initial MVP audit had not detected it)
- Ghidra headless: **12.1.2 real smoke confirmed with JDK 21**

## Starting address hypotheses

The following are public-analysis leads copied from `Agents.md`, not confirmed facts for this disc revision:

| Address | Hypothesized role | Confidence |
|---|---|---|
| `0x800AC064` | ~30 Hz frame-related value | unverified |
| `0x800AC0D0` | player X | unverified |
| `0x800AC0D4` | player Y | unverified |
| `0x800AC0D8` | player Z | unverified |
| `0x800AC104` | vehicle heading | unverified |
| `0x800AC288` | speed | unverified |
| `0x800AC32C` | RPM | unverified |
| `0x801FFF58` | cockpit camera X | unverified |

## First dynamic evidence to collect

Verify target identity and value cadence, then capture write PCs for `0x800AC064` and vehicle coordinates, read PCs for those coordinates during rendering, and camera read/write PCs. Every hit must include VBlank, PC, RA, SP, relevant GPRs, accessed address/width, and dropped-event count. Only then export the surrounding functions and callers in Ghidra.

Boot/title Read/Write PCs for the camera candidate are recorded in `docs/FIRST_R4_OBSERVATION.md`. Race functions and the other candidate semantics remain unconfirmed. No patch is proposed.

## Deterministic race evidence — 2026-07-17

The validated Japanese race state disproves the published vehicle/frame candidates for this build: `0x800AC064`, `0x800AC0D0/D4/D8`, `0x800AC104`, `0x800AC288`, and `0x800AC32C` remained zero over 600 moving-race VBlanks and produced no bounded accesses in their configured phases.

`0x801FFF58` changed at approximately 30 Hz and produced bounded Read/Write events, but lies immediately below the observed stack pointer and was accessed by many unrelated PCs. It is classified as **dynamic stack-region evidence, camera semantics unconfirmed/rejected**. See `docs/RACE_TRACE.md` for exact sources and limits.

Real Ghidra mapping confirms the frequent pairs are stack traffic: `0x80050194` / `0x800501B0` are `sw` / `lw ra,0x10(sp)` in `FUN_80050168`, while `0x80084C28` / `0x80084D2C` are `sw` / `lw s4,0x20(sp)` in `FUN_80084c10`. This is static corroboration that the watched address was whichever stack slot happened to occupy `0x801FFF58`, not a stable camera global.

## Confirmed race structure and cadence

- Active overlay entry: `0x80114780`, called 300 times over 600 VBlanks.
- Player pointer: `0x800FFA00 -> 0x800ABCE0`.
- Position fields: object offsets `+0x10/+0x14/+0x18`; X/Z change at approximately 30 Hz.
- Camera transform consumes position and orientation offsets `+0x50/+0x54/+0x58` in `FUN_80034178` at 30 Hz.
- `FUN_80038338` dispatches player/AI vehicle updates at 30 Hz.
- `FUN_8003C838` performs lap/progress timer logic at 30 Hz.
- Raw display hashes change exactly every two VBlanks (29.97 Hz).

The evidence is consolidated in `docs/R4_TIMING_MODEL.md`. RPM and a render-only 60 Hz path remain unidentified, so no patch candidate is authorized.
