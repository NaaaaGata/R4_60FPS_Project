# Static analysis bridge

## Verified local environment

The official NSA Ghidra 12.1.2 release (`Ghidra_12.1.2_build`, published 2026-06-05) is installed under ignored `private/tools/ghidra/`. The downloaded official asset `ghidra_12.1.2_PUBLIC_20260605.zip` matched its GitHub release SHA-256 `b62e81a0390618466c019c60d8c2f796ced2509c4c1aea4a37644a77272cf99d`. Headless runs use OpenJDK 21.0.11. The ignored local project config registers `support/analyzeHeadless`; no administrator installation or unofficial mirror was used.

Official references: [Ghidra release repository](https://github.com/NationalSecurityAgency/ghidra), [Getting Started](https://github.com/NationalSecurityAgency/ghidra/blob/master/GhidraDocs/GettingStarted.md), and the installed official `support/analyzeHeadlessREADME.html`.

## Reproducible PS-X EXE import

For a verified `PS-X EXE`, `ghidra-export` parses the header and supplies only confirmed BinaryLoader options:

- processor `MIPS:LE:32:default`;
- `-loader BinaryLoader`;
- base address `0x80010000`;
- file offset `0x800` so the PS-X header is not disassembled as payload;
- payload length `0x9C000` (638,976 bytes);
- block name `R4_PAYLOAD`;
- entry point `0x8007D4B4`.

`R4Prepare.java` fails if the resulting payload block is not exactly `0x80010000–0x800ABFFF`, then creates/disassembles the verified entry point before automatic analysis. `R4Export.java` emits hashes, language, mapped memory blocks, function ranges and file offsets, basic blocks, calls, xrefs, strings, overlays, bounded requested-address disassembly with delay-slot/flow metadata, computed jumps in selected functions, and selected-function decompiler output. Cache identity covers the input and both scripts.

## Real smoke result

The extracted executable hash matched `95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775`. Ghidra successfully produced 1,456 function candidates, 16,979 basic blocks, 3,034 call edges, 251 strings, and selected decompilation for three functions. The output reports analysis base `0x80010000` and one 638,976-byte `R4_PAYLOAD` block.

Dynamic/static correlation rejected the public camera label at `0x801FFF58`: frequent dynamic writers/readers are ordinary stack prologues/epilogues (`sw/lw ra,0x10(sp)` and `sw/lw s4,0x20(sp)`). Ghidra function boundaries and pseudocode remain hypotheses; MIPS delay slots, bad-data warnings, overlays, and inferred signatures require dynamic confirmation.

The first two real attempts are retained locally as failed evidence: one exposed a Ghidra 12.1.2 string-iterator API incompatibility and an incorrectly decimal-formatted BinaryLoader length; the next exposed incomplete JSON control-character escaping. Both fail-closed paths were corrected and covered by tests before the successful export.

## Runtime overlay mapping

`probe-overlay` compares a bounded runtime fingerprint against owned disc files and can extract only an explicitly bounded matching region into ignored `private/extracted/`. It found race overlay candidates in `R4.BIN` at `0x261A000` and `0x2660000`, separated by `0x46000` bytes. The active runtime entry at `0x80114780` is offset `0x90` from mapped base `0x801146F0`.

Raw overlay import is explicit and cache-keyed:

```bash
r4-autolab ghidra-export \
  --input private/extracted/overlays/r4-bin-0261a000.bin \
  --binary-base 0x801146F0 --binary-length 0x46000 \
  --entry-point 0x80114780 --block-name R4_OVERLAY
```

The real overlay export produced 504 function candidates and 494 direct call edges. The region contains mutable data as well as code, so Ghidra output remains a hypothesis and every selected function is dynamically correlated before being assigned a role.
