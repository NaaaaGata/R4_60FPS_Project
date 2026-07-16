from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from collections import Counter

from ..emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from ..emulator.transport import TcpJsonlTransport
from ..models import BreakpointSpec, LaunchConfig
from .cadence import analyze_cadence


R4_STARTING_WATCHES = [
    {"name": "frame_candidate", "address": 0x800AC064, "width": 4},
    {"name": "player_x_candidate", "address": 0x800AC0D0, "width": 4},
    {"name": "player_y_candidate", "address": 0x800AC0D4, "width": 4},
    {"name": "player_z_candidate", "address": 0x800AC0D8, "width": 4},
    {"name": "heading_candidate", "address": 0x800AC104, "width": 4},
    {"name": "speed_candidate", "address": 0x800AC288, "width": 4},
    {"name": "rpm_candidate", "address": 0x800AC32C, "width": 4},
    {"name": "camera_x_candidate", "address": 0x801FFF58, "width": 4},
]


def observe_r4_boot(
    executable: Path,
    lua_bootstrap: Path,
    cue_path: Path,
    run_dir: Path,
    vblanks: int,
    timeout_seconds: float,
) -> dict[str, Any]:
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
            iso=cue_path,
        ),
        transport,
    )
    breakpoint_ids: list[str] = []
    breakpoint_map: dict[str, dict[str, Any]] = {}
    try:
        adapter.launch(LaunchConfig("r4-boot-observation", run_dir, timeout_seconds))
        adapter.connect()
        handshake = adapter.handshake()
        adapter.pause()
        configured = adapter.configure_watches(R4_STARTING_WATCHES)
        for watch in R4_STARTING_WATCHES:
            address = watch["address"]
            width = watch["width"]
            if not isinstance(address, int) or not isinstance(width, int):
                raise TypeError("watch address and width must be integers")
            for access in ("write", "read"):
                identifier = adapter.set_breakpoint(BreakpointSpec(address, access, width, 16))
                breakpoint_ids.append(identifier)
                breakpoint_map[identifier] = {"name": watch["name"], "address": address, "access": access}
        transport.drain_events()
        adapter.run_vblanks(vblanks)
        adapter.pause()
        events = transport.drain_events()
        for identifier in breakpoint_ids:
            adapter.clear_breakpoint(identifier)
        breakpoint_ids.clear()
        adapter.capture_screenshot(run_dir / "final")
        vblank_events = [event for event in events if event.get("event") == "vblank"]
        breakpoint_events = [event for event in events if event.get("event") == "breakpoint"]
        cadences: dict[str, Any] = {}
        for watch in R4_STARTING_WATCHES:
            name = str(watch["name"])
            flattened = [
                {**event, "watch": dict(event.get("watch_values", {})).get(name)} for event in vblank_events
            ]
            cadences[name] = analyze_cadence(flattened, "watch").to_dict() if flattened else None
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        source_counts = Counter(
            (
                str(event.get("breakpoint_id")),
                str(event.get("access", "unknown")),
                int(event.get("accessed_address", 0)),
                int(event.get("pc", 0)),
                int(event.get("ra", 0)),
            )
            for event in breakpoint_events
        )
        report = {
            "created_at": datetime.now(UTC).isoformat(),
            "classification": "boot_observation_only",
            "handshake": handshake,
            "configured_watches": configured,
            "requested_vblanks": vblanks,
            "observed_vblanks": len(vblank_events),
            "breakpoint_events": len(breakpoint_events),
            "breakpoint_sources": [
                {
                    "breakpoint_id": key[0],
                    "watch": breakpoint_map.get(key[0], {}).get("name", "unknown"),
                    "access": key[1],
                    "accessed_address": f"0x{key[2]:08X}",
                    "pc": f"0x{key[3]:08X}",
                    "ra": f"0x{key[4]:08X}",
                    "count": count,
                }
                for key, count in sorted(source_counts.items())
            ],
            "cadences": cadences,
            "limitations": [
                "No deterministic race save state or input was loaded.",
                "Values observed during boot/title flow cannot confirm race semantics.",
                "No memory write or patch was performed by R4 AutoLab.",
            ],
        }
        (run_dir / "observation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report
    finally:
        for identifier in breakpoint_ids:
            try:
                adapter.clear_breakpoint(identifier)
            except Exception:
                pass
        adapter.shutdown()
