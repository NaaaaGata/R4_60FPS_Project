from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .analysis.cadence import analyze_cadence
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


@dataclass(frozen=True)
class TargetWatch:
    name: str
    address: int
    width: int

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "address": self.address, "width": self.width}


def parse_target_watch(value: str) -> TargetWatch:
    try:
        name, address_text, width_text = value.split(":", 2)
        address = int(address_text, 0)
        width = int(width_text, 0)
    except (ValueError, TypeError) as error:
        raise ValueError("watch must use name:address:width") from error
    if not name or not name.replace("_", "").isalnum():
        raise ValueError("watch name must be alphanumeric with optional underscores")
    if width not in {1, 2, 4} or address < 0x80000000 or address > 0x801FFFFF - width + 1:
        raise ValueError("watch must be 1/2/4 bytes inside PS1 main RAM")
    return TargetWatch(name, address, width)


def trace_targeted_addresses(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    watches: tuple[TargetWatch, ...],
    *,
    vblanks: int = 600,
    max_write_hits: int = 32,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if not watches or len(watches) > 16:
        raise ValueError("between 1 and 16 targeted watches are required")
    if len({watch.name for watch in watches}) != len(watches):
        raise ValueError("targeted watch names must be unique")
    if vblanks < 120 or vblanks > 3600:
        raise ValueError("vblanks must be between 120 and 3600")
    if max_write_hits <= 0 or max_write_hits > 128:
        raise ValueError("max_write_hits must be between 1 and 128")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "targeted-trace" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    state_hash = sha256_file(state)
    scenario = InputScenario(f"accelerate-targeted-{vblanks}", vblanks, ("CROSS",))
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
    failures: list[str] = []
    vblank_events: list[dict[str, Any]] = []
    breakpoint_events: list[dict[str, Any]] = []
    try:
        adapter.launch(LaunchConfig("targeted-address-trace", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        adapter.load_state(state)
        adapter.configure_watches([watch.to_dict() for watch in watches])
        adapter.clear_pad_buttons()
        for watch in watches:
            identifiers.append(
                adapter.set_breakpoint(
                    BreakpointSpec(watch.address, "write", watch.width, max_write_hits)
                )
            )
        transport.drain_events()
        adapter.set_pad_buttons(list(scenario.buttons))
        adapter.run_vblanks(vblanks)
        adapter.pause()
        adapter.clear_pad_buttons()
        events = transport.drain_events()
        identity = {
            "scenario": scenario.name,
            "state_sha256": state_hash,
            "input_sha256": scenario.sha256,
        }
        vblank_events = [{**event, **identity} for event in events if event.get("event") == "vblank"]
        breakpoint_events = [
            {
                **event,
                **identity,
                "old_value": None,
                "new_value": None,
                "value_limitation": "PCSX callback does not expose access values",
            }
            for event in events
            if event.get("event") == "breakpoint"
        ]
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

    for filename, events in (("telemetry.jsonl", vblank_events), ("breakpoints.jsonl", breakpoint_events)):
        with (run_dir / filename).open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
    results: list[dict[str, Any]] = []
    for watch in watches:
        flattened = [
            {**event, "watch": dict(event.get("watch_values", {})).get(watch.name)}
            for event in vblank_events
        ]
        watch_hits = [
            event for event in breakpoint_events if int(event["accessed_address"]) == watch.address
        ]
        results.append(
            {
                "watch": watch.to_dict(),
                "cadence": analyze_cadence(flattened, "watch").to_dict() if flattened else None,
                "write_hits": len(watch_hits),
                "write_sources": sorted(
                    {
                        (f"0x{int(event['pc']):08X}", f"0x{int(event['ra']):08X}")
                        for event in watch_hits
                    }
                ),
                "first_value": flattened[0]["watch"] if flattened else None,
                "last_value": flattened[-1]["watch"] if flattened else None,
            }
        )
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if len(vblank_events) >= vblanks and not failures else "FAIL",
        "vblanks": len(vblank_events),
        "state_sha256": state_hash,
        "input_sha256": scenario.sha256,
        "results": results,
        "breakpoint_events": len(breakpoint_events),
        "failures": failures,
        "limitations": [
            "Addresses were selected from dynamic/static evidence; this command does not search RAM.",
            "Write events are capped per watch and old/new access values remain unavailable.",
            "No memory write or patch was performed.",
        ],
    }
    report_path = run_dir / "targeted-trace.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
