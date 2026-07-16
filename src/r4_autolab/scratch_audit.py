from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


SCRATCH_START = 0x1F800000
SCRATCH_END = 0x1F800400


def validate_scratch_address(address: int, width: int = 4) -> None:
    if width != 4 or address % width:
        raise ValueError("scratch audit requires an aligned 4-byte location")
    if not SCRATCH_START <= address <= SCRATCH_END - width:
        raise ValueError("scratch address must be inside 0x1F800000..0x1F8003FF")


def evaluate_scratch_samples(samples: list[dict[str, Any]], events: list[dict[str, Any]]) -> tuple[str, list[str]]:
    unchanged = bool(samples) and all(sample["before_hex"] == sample["after_hex"] for sample in samples)
    same_initial = bool(samples) and len({sample["before_hex"] for sample in samples}) == 1
    no_access = not events
    reasons = [
        f"all_scenarios_unchanged={unchanged}",
        f"same_state_initial_bytes={same_initial}",
        f"read_write_breakpoint_hits={len(events)}",
    ]
    return ("PASS" if unchanged and same_initial and no_access else "FAIL"), reasons


def audit_scratch_location(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    address: int,
    scenarios: tuple[InputScenario, ...],
    *,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    validate_scratch_address(address)
    if not scenarios or len(scenarios) > 8:
        raise ValueError("between 1 and 8 scratch audit scenarios are required")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "scratch-audit" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    transport = TcpJsonlTransport()
    adapter = PCSXReduxAdapter(
        PCSXLaunchOptions(
            executable=executable,
            lua_bootstrap=lua_bootstrap,
            run=True,
            stdout=True,
            lua_stdout=True,
            interpreter=True,
            debugger=True,
            testmode=True,
            portable_directory=run_dir / "portable",
            bios=assets.bios,
            iso=assets.cue,
        ),
        transport,
    )
    identifiers: list[str] = []
    samples: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        adapter.launch(LaunchConfig("scratch-audit", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        identifiers = [
            adapter.set_breakpoint(BreakpointSpec(address, "read", 4, 1)),
            adapter.set_breakpoint(BreakpointSpec(address, "write", 4, 1)),
        ]
        for scenario in scenarios:
            adapter.load_state(state)
            adapter.clear_pad_buttons()
            before = adapter.read_memory(address, 4)
            transport.drain_events()
            adapter.set_pad_buttons(list(scenario.buttons))
            adapter.run_vblanks(scenario.vblanks)
            adapter.pause()
            adapter.clear_pad_buttons()
            after = adapter.read_memory(address, 4)
            scenario_events = [
                {**event, "scenario": scenario.name, "input_sha256": scenario.sha256}
                for event in transport.drain_events()
                if event.get("event") == "breakpoint"
            ]
            events.extend(scenario_events)
            samples.append(
                {
                    "scenario": scenario.to_dict(),
                    "input_sha256": scenario.sha256,
                    "before_hex": before.hex(),
                    "after_hex": after.hex(),
                    "breakpoint_hits": len(scenario_events),
                }
            )
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        for identifier in identifiers:
            try:
                adapter.clear_breakpoint(identifier)
            except Exception:
                pass
        try:
            adapter.clear_pad_buttons()
        except Exception:
            pass
        try:
            adapter.shutdown()
        except Exception as error:
            failures.append(f"shutdown: {type(error).__name__}: {error}")

    status, reasons = evaluate_scratch_samples(samples, events)
    if failures:
        status = "FAIL"
    with (run_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": status,
        "address": f"0x{address:08X}",
        "width": 4,
        "state_sha256": sha256_file(state),
        "total_vblanks": sum(scenario.vblanks for scenario in scenarios),
        "samples": samples,
        "breakpoint_events": events,
        "reasons": reasons,
        "failures": failures,
        "decision": (
            "eligible only for a paused transient write/read/restore capability test"
            if status == "PASS"
            else "not eligible for any write test"
        ),
        "limitations": [
            "No finite trace proves an address is unused in every game mode.",
            "PASS authorizes only an immediate paused restoration test, never game data or code storage.",
            "Read/write breakpoints were capped at one hit each and no memory write was performed.",
        ],
    }
    report_path = run_dir / "scratch-audit.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
