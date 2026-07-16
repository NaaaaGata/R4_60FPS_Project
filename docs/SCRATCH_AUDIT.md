# Scratchpad safety audit

This audit concerns only `0x1F8003FC..0x1F8003FF`, the final aligned word of the PS1 1 KiB scratchpad. It does not classify any R4 RAM address as safe and does not authorize storing experiment state there while the game runs.

## Read-only gate

The verified race state was reloaded for all five deterministic input scenarios: neutral, accelerate, left, right, and accelerate-plus-left. Read and Write breakpoints covered the candidate word for a total of 1,920 VBlanks. The word was `00000000` before and after every scenario, with zero breakpoint events. This finite trace cannot prove universal non-use; it authorizes only an immediate write/read/restore while paused.

Command:

```bash
r4-autolab audit-scratch --address 0x1F8003FC --timeout 60
```

## Write/restore result

The first explicit capability attempt failed safely: `getMemoryAsFile().writeAt()` acknowledged four bytes but read-back did not match. The `finally` restoration path ran, shutdown passed, and no child remained. Exact report: `runs/capabilities/pcsx-20260716T190812187819Z/capabilities.json` (ignored/local).

Official PCSX-Redux documentation defines `PCSX.getScratchPtr()` as the direct pointer for exactly 1 KiB of scratchpad. The host now uses it only when the already validated request lies wholly inside that 1 KiB range; all other memory keeps the safer `getMemoryAsFile()` path. The full 1,920-VBlank read-only gate was rerun after this change and passed again.

The second explicit test then completed:

```text
original     00000000
replacement  a5a5a5a5
read-back    a5a5a5a5
restored     00000000
```

Capability report `runs/capabilities/pcsx-20260716T191043958745Z/capabilities.json` records PASS for scratch write, shutdown, and process cleanup. Both reports remain ignored because they are environment artifacts.

This proves bridge restoration mechanics at one non-code scratch word. It is not evidence for a 60 fps patch and does not permit writes to published R4 candidate addresses.
