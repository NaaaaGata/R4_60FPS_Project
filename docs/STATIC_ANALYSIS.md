# Static analysis bridge

Phase 4 provides a reproducible Ghidra Headless boundary without downloading or bundling Ghidra. Detection checks `R4_AUTOLAB_GHIDRA_HEADLESS`, `PATH`, `/Applications`, and `~/Applications`. The local audit found no `analyzeHeadless`, so only the fake integration path is executable on this Mac.

The command is:

```bash
r4-autolab ghidra-export --input /private/path/PSX.EXE --address 0x80010000
```

Add `--fake` to validate orchestration without Ghidra. Output is cached by input SHA-256, export-script SHA-256, addresses, and processor selection under `runs/static-cache/`. The runner uses argument arrays, a per-run project, an analysis timeout, `-import`, `-scriptPath`, `-postScript R4Export.java`, and `-deleteProject`. These options follow Ghidra's official Headless Analyzer interface: [Getting Started](https://github.com/NationalSecurityAgency/ghidra/blob/master/GhidraDocs/GettingStarted.md) and [AnalyzeHeadless source](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/java/ghidra/app/util/headless/AnalyzeHeadless.java).

`ghidra_scripts/R4Export.java` exports input hash, language, image base, functions, basic blocks, function calls, requested-address xrefs, defined strings, overlay memory blocks, and requested-address disassembly as JSON. It cannot be compiled or smoke-tested until Ghidra is installed. No decompiler output is treated as truth.

Real analysis resume requirements:

1. Install an official Ghidra release and compatible JDK independently.
2. Set `R4_AUTOLAB_GHIDRA_HEADLESS` to its absolute `support/analyzeHeadless` path.
3. Extract the owned disc's PS-X EXE into an ignored private path and verify its SHA-256/load metadata.
4. Confirm the installed Ghidra language/loader ID before supplying `--processor`; no processor ID is guessed by default.
5. Run one requested-address export and review the log before broadening scope.
