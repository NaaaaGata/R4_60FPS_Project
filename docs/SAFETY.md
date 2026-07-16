# Safety

- Original discs/images, BIOS, save data, and executables are immutable inputs and ignored by Git.
- The supervisor accepts structured proposals only; the research agent cannot write RAM directly.
- Patch target identity, address range, alignment, width, byte lengths, expected original bytes, evidence, and change count are validated.
- One independent change is allowed per MVP experiment.
- Restoration receipts are captured before writes and replayed in reverse order during normal and exceptional cleanup.
- Safety violations and restoration failures are quarantined and recorded in SQLite.
- Real mode is fail-closed until a verified emulator transport is provided.
- Campaign defaults to dry-run and requires explicit finite budgets.
- No downloader, disc writer, BIOS writer, brute-force address search, or unbounded recursive Codex execution exists.

Known gap: the current Python supervisor relies on the real bridge to enforce request timeouts while an operation is in progress. The production bridge must prove timeout and process-residue cleanup before real patching is enabled.

