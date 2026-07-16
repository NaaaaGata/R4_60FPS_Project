# R4 race-state validation

The private raw state captured on 2026-07-17 JST has SHA-256 `a80f4a2c1dead74c41e309fe0762b397e635e390ba46ce8251f016b3c595c1e7` and size 19,063,530 bytes. The state and raw pixels remain ignored; their relative locations and identity metadata are retained so the owned local copy can be reproduced without publishing game content.

Three independent PCSX-Redux processes loaded the state and advanced it by 60 VBlanks. Every attempt produced identical initial candidate values, identical post-advance candidate values, identical initial screenshot hashes, and identical final screenshot hashes. All processes shut down cleanly. The classification is **PASS**.

Pause landed at `PC=0x80000080` in every attempt. This is the standard PS1 general exception vector, while `RA=0x8008AFCC` returns into the verified R4 payload. The validator accepts either a PC directly in the payload or this exception-vector context with a target RA. It does not accept a BIOS PC with a non-target RA.

The image is a valid 320×240×16-bpp active-race frame. However, the public player/frame/speed/RPM candidate addresses read zero while the HUD showed a moving car. Those addresses therefore remain unconfirmed for this Japanese executable and will not be written. Race discovery must proceed through bounded read-only watches and breakpoints.
