from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .analysis.cadence import analyze_cadence
from .analysis.observation import R4_STARTING_WATCHES
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


def _watch(name: str) -> dict[str, Any]:
    return next(item for item in R4_STARTING_WATCHES if item["name"] == name)


RACE_BREAKPOINT_PHASES: tuple[tuple[str, str, tuple[dict[str, Any], ...]], ...] = (
    ("frame-write", "write", (_watch("frame_candidate"),)),
    (
        "player-xyz-write",
        "write",
        (_watch("player_x_candidate"), _watch("player_y_candidate"), _watch("player_z_candidate")),
    ),
    ("speed-write", "write", (_watch("speed_candidate"),)),
    ("rpm-write", "write", (_watch("rpm_candidate"),)),
    ("heading-write", "write", (_watch("heading_candidate"),)),
    ("camera-write", "write", (_watch("camera_x_candidate"),)),
    (
        "player-xyz-read",
        "read",
        (_watch("player_x_candidate"), _watch("player_y_candidate"), _watch("player_z_candidate")),
    ),
    ("camera-read", "read", (_watch("camera_x_candidate"),)),
)


def _new_adapter(
    executable: Path,
    lua_bootstrap: Path,
    assets: CaptureAssets,
    run_dir: Path,
) -> tuple[PCSXReduxAdapter, TcpJsonlTransport]:
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
    return adapter, transport


def enrich_breakpoint_event(
    event: dict[str, Any],
    *,
    phase: str,
    scenario: str,
    state_sha256: str,
    input_sha256: str,
) -> dict[str, Any]:
    return {
        **event,
        "phase": phase,
        "scenario": scenario,
        "state_sha256": state_sha256,
        "input_sha256": input_sha256,
        "old_value": None,
        "new_value": None,
        "value_limitation": (
            "PCSX-Redux breakpoint callback does not expose old/new values; "
            "post-phase memory is not attributed to an individual hit"
        ),
    }


def summarize_breakpoint_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        (
            str(event["phase"]),
            str(event["access"]),
            int(event["accessed_address"]),
            int(event["access_width"]),
            int(event["pc"]),
            int(event["ra"]),
        )
        for event in events
    )
    return [
        {
            "phase": key[0],
            "access": key[1],
            "address": f"0x{key[2]:08X}",
            "width": key[3],
            "pc": f"0x{key[4]:08X}",
            "ra": f"0x{key[5]:08X}",
            "count": count,
        }
        for key, count in sorted(counts.items())
    ]


def _read_watches(adapter: PCSXReduxAdapter) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for watch in R4_STARTING_WATCHES:
        name = watch["name"]
        address = watch["address"]
        width = watch["width"]
        if not isinstance(name, str) or not isinstance(address, int) or not isinstance(width, int):
            raise TypeError("invalid built-in watch")
        data = adapter.read_memory(address, width)
        unsigned = int.from_bytes(data, "little")
        signed = int.from_bytes(data, "little", signed=True)
        result[name] = {"hex": data.hex(), "unsigned_le": unsigned, "signed_le": signed}
    return result


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def trace_r4_race(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    *,
    telemetry_vblanks: int = 600,
    breakpoint_vblanks: int = 120,
    max_hits: int = 32,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if telemetry_vblanks < 120 or telemetry_vblanks > 3600:
        raise ValueError("telemetry_vblanks must be between 120 and 3600")
    if breakpoint_vblanks <= 0 or breakpoint_vblanks > 600:
        raise ValueError("breakpoint_vblanks must be between 1 and 600")
    if max_hits <= 0 or max_hits > 128:
        raise ValueError("max_hits must be between 1 and 128")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "race-trace" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    state_hash = sha256_file(state)
    telemetry_input = InputScenario(f"accelerate-trace-{telemetry_vblanks}", telemetry_vblanks, ("CROSS",))
    phase_input = InputScenario(f"accelerate-trace-{breakpoint_vblanks}", breakpoint_vblanks, ("CROSS",))
    failures: list[str] = []
    vblank_events: list[dict[str, Any]] = []

    baseline_dir = run_dir / "telemetry"
    baseline_adapter, baseline_transport = _new_adapter(executable, lua_bootstrap, assets, baseline_dir)
    try:
        baseline_adapter.launch(LaunchConfig("race-telemetry", baseline_dir, timeout_seconds))
        baseline_adapter.connect()
        baseline_adapter.handshake()
        baseline_adapter.pause()
        baseline_adapter.load_state(state)
        baseline_adapter.configure_watches(R4_STARTING_WATCHES)
        baseline_adapter.clear_pad_buttons()
        baseline_transport.drain_events()
        baseline_adapter.set_pad_buttons(list(telemetry_input.buttons))
        baseline_adapter.run_vblanks(telemetry_vblanks)
        baseline_adapter.pause()
        baseline_adapter.clear_pad_buttons()
        vblank_events = [
            {
                **event,
                "scenario": telemetry_input.name,
                "state_sha256": state_hash,
                "input_sha256": telemetry_input.sha256,
            }
            for event in baseline_transport.drain_events()
            if event.get("event") == "vblank"
        ]
        baseline_adapter.capture_screenshot(baseline_dir / "final")
    except Exception as error:
        failures.append(f"telemetry: {type(error).__name__}: {error}")
    finally:
        try:
            baseline_adapter.clear_pad_buttons()
        except Exception:
            pass
        try:
            baseline_adapter.shutdown()
        except Exception as error:
            failures.append(f"telemetry shutdown: {type(error).__name__}: {error}")
    _write_jsonl(run_dir / "telemetry.jsonl", vblank_events)

    breakpoint_events: list[dict[str, Any]] = []
    phase_results: list[dict[str, Any]] = []
    for phase_name, access, watches in RACE_BREAKPOINT_PHASES:
        phase_dir = run_dir / "breakpoints" / phase_name
        adapter, transport = _new_adapter(executable, lua_bootstrap, assets, phase_dir)
        identifiers: list[str] = []
        try:
            adapter.launch(LaunchConfig(phase_name, phase_dir, timeout_seconds))
            adapter.connect()
            adapter.handshake()
            adapter.pause()
            adapter.load_state(state)
            adapter.configure_watches(R4_STARTING_WATCHES)
            adapter.clear_pad_buttons()
            for watch in watches:
                address = watch["address"]
                width = watch["width"]
                if not isinstance(address, int) or not isinstance(width, int):
                    raise TypeError("invalid breakpoint watch")
                identifiers.append(adapter.set_breakpoint(BreakpointSpec(address, access, width, max_hits)))
            transport.drain_events()
            adapter.set_pad_buttons(list(phase_input.buttons))
            adapter.run_vblanks(breakpoint_vblanks)
            adapter.pause()
            adapter.clear_pad_buttons()
            raw_events = transport.drain_events()
            phase_breakpoints = [
                enrich_breakpoint_event(
                    event,
                    phase=phase_name,
                    scenario=phase_input.name,
                    state_sha256=state_hash,
                    input_sha256=phase_input.sha256,
                )
                for event in raw_events
                if event.get("event") == "breakpoint"
            ]
            breakpoint_events.extend(phase_breakpoints)
            phase_results.append(
                {
                    "phase": phase_name,
                    "access": access,
                    "addresses": [f"0x{int(watch['address']):08X}" for watch in watches],
                    "vblanks": breakpoint_vblanks,
                    "max_hits_per_breakpoint": max_hits,
                    "hits": len(phase_breakpoints),
                    "values_after_phase": _read_watches(adapter),
                }
            )
        except Exception as error:
            failures.append(f"{phase_name}: {type(error).__name__}: {error}")
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
                failures.append(f"{phase_name} shutdown: {type(error).__name__}: {error}")
    _write_jsonl(run_dir / "breakpoints.jsonl", breakpoint_events)

    cadences: dict[str, Any] = {}
    for watch in R4_STARTING_WATCHES:
        name = str(watch["name"])
        flattened = [
            {**event, "watch": dict(event.get("watch_values", {})).get(name)}
            for event in vblank_events
        ]
        cadences[name] = analyze_cadence(flattened, "watch").to_dict() if flattened else None
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if len(vblank_events) >= telemetry_vblanks and not failures else "FAIL",
        "classification": "race_read_only_trace",
        "serial": assets.identity.disc_serial,
        "executable_sha256": assets.identity.sha256,
        "state_sha256": state_hash,
        "telemetry_input_sha256": telemetry_input.sha256,
        "breakpoint_input_sha256": phase_input.sha256,
        "requested_telemetry_vblanks": telemetry_vblanks,
        "observed_telemetry_vblanks": len(vblank_events),
        "breakpoint_events": len(breakpoint_events),
        "phases": phase_results,
        "sources": summarize_breakpoint_events(breakpoint_events),
        "cadences": cadences,
        "failures": failures,
        "limitations": [
            "No candidate address was written and no RAM patch was applied.",
            "Breakpoint old/new values are unavailable in this PCSX callback and remain null.",
            "Published candidate semantics remain unconfirmed when visible race state contradicts their values.",
        ],
    }
    report_path = run_dir / "race-trace.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
