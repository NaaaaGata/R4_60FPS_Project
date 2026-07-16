# Reverse-engineering notebook

## Target identity

- Serial: `SLPS-01800` (**confirmed from SYSTEM.CNF and PCSX disc ID**)
- Executable SHA-256: `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775`
- Load address: `0x80010000`
- Initial PC: `0x8007D4B4`
- Observed disc-image SHA-256: `72e54ea4bf6da5a2e839a355e9dcacae989fcddcab84b85cbbb4b2ff08f4a716` (622,452,096-byte user-provided `.bin`; this is **not** the executable hash)
- Observed CUE SHA-256: `139eedfa188f0612f30bca2c0e9fb6d2fdbfd2502a9dc71fceafd73da3011e95` (80-byte user-provided `.cue`)
- PCSX-Redux version/API: **not installed or not detected at MVP audit**
- Ghidra headless: **not detected at MVP audit**

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
