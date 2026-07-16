from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .ai_trace import PLAYER_OBJECT
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


PAIR_FIELDS = {
    "current_x": (0x10, 4, True), "current_y": (0x14, 4, True), "current_z": (0x18, 4, True),
    "recorded_x": (0x20, 4, True), "recorded_y": (0x24, 4, True), "recorded_z": (0x28, 4, True),
    "delta_x": (0x40, 4, True), "delta_y": (0x44, 4, True), "delta_z": (0x48, 4, True),
    "orientation_x": (0x50, 4, True), "orientation_y": (0x54, 4, True), "orientation_z": (0x58, 4, True),
    "orientation_copy_x": (0x80, 2, True), "orientation_copy_y": (0x82, 2, True), "orientation_copy_z": (0x84, 2, True),
    "render_x": (0xC8, 4, True), "render_y": (0xCC, 4, True), "render_z": (0xD0, 4, True),
    "render_aux": (0xD4, 4, True),
}


def compare_state_pair(samples: list[dict[str, int]], current: str, candidate: str) -> dict[str, Any]:
    if not samples:
        raise ValueError("state-pair comparison needs samples")
    same = sum(sample[current] == sample[candidate] for sample in samples)
    previous = sum(
        samples[index][candidate] == samples[index - 1][current]
        for index in range(1, len(samples))
    )
    return {
        "samples": len(samples),
        "same_frame_matches": same,
        "previous_frame_matches": previous,
        "same_frame_ratio": same / len(samples),
        "previous_frame_ratio": previous / max(1, len(samples) - 1),
    }


def _decode_fields(data: bytes) -> dict[str, int]:
    result: dict[str, int] = {}
    for name, (offset, width, signed) in PAIR_FIELDS.items():
        result[name] = int.from_bytes(data[offset:offset + width], "little", signed=signed)
    return result


def trace_state_pairs(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    scenario: InputScenario,
    *,
    vblanks: int = 120,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if not 120 <= vblanks <= 600 or scenario.vblanks < vblanks:
        raise ValueError("state-pair trace needs 120..600 scenario VBlanks")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "state-pairs" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    transport = TcpJsonlTransport()
    adapter = PCSXReduxAdapter(
        PCSXLaunchOptions(
            executable=executable, lua_bootstrap=lua_bootstrap,
            run=True, stdout=True, lua_stdout=True, interpreter=True, debugger=True, testmode=True,
            portable_directory=run_dir / "portable", bios=assets.bios, iso=assets.cue, read_only=True,
        ),
        transport,
    )
    identifiers: list[str] = []
    samples: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    failures: list[str] = []
    ai_pointer = 0
    try:
        adapter.launch(LaunchConfig("state-pairs", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        adapter.load_state(state)
        adapter.clear_pad_buttons()
        ai_pointer = int.from_bytes(adapter.read_memory(0x800FFA04, 4), "little")
        if not 0x80010000 <= ai_pointer <= 0x801FFFFF - 0xD8:
            raise RuntimeError(f"first AI pointer invalid: 0x{ai_pointer:08X}")
        for address in (0x8002ECD0, 0x80034178):
            identifiers.append(adapter.set_breakpoint(BreakpointSpec(address, "execute", 4, vblanks)))
        transport.drain_events()
        adapter.set_pad_buttons(list(scenario.buttons))
        for relative_vblank in range(1, vblanks + 1):
            adapter.run_vblanks(1)
            adapter.pause()
            events.extend(event for event in transport.drain_events() if event.get("event") == "breakpoint")
            player = _decode_fields(adapter.read_memory(PLAYER_OBJECT, 0xD8))
            ai = _decode_fields(adapter.read_memory(ai_pointer, 0xD8))
            samples.append(
                {
                    "relative_vblank": relative_vblank,
                    "frame_counter": int.from_bytes(adapter.read_memory(0x800ABC94, 4), "little"),
                    "player": player,
                    "ai": ai,
                    "camera_scratch": {
                        "x": int.from_bytes(adapter.read_memory(0x1F800008, 4), "little", signed=True),
                        "y": int.from_bytes(adapter.read_memory(0x1F80000C, 4), "little", signed=True),
                        "z": int.from_bytes(adapter.read_memory(0x1F800010, 4), "little", signed=True),
                        "target_or_aux": int.from_bytes(adapter.read_memory(0x1F800014, 4), "little", signed=True),
                    },
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
    active_samples = [
        sample for index, sample in enumerate(samples)
        if index == 0 or sample["frame_counter"] != samples[index - 1]["frame_counter"]
    ]
    comparisons: dict[str, Any] = {}
    for owner in ("player", "ai"):
        owner_samples = [dict(sample[owner]) for sample in active_samples]
        comparisons[owner] = {
            axis: {
                "render_copy": compare_state_pair(owner_samples, f"current_{axis}", f"render_{axis}"),
                "recorded_source": compare_state_pair(owner_samples, f"current_{axis}", f"recorded_{axis}"),
            }
            for axis in ("x", "y", "z")
        }
    event_counts = {
        f"0x{address:08X}": sum(int(event["accessed_address"]) == address for event in events)
        for address in (0x8002ECD0, 0x80034178)
    }
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if len(samples) == vblanks and not failures else "FAIL",
        "state_sha256": sha256_file(state),
        "input_sha256": scenario.sha256,
        "vblanks": vblanks,
        "active_samples": len(active_samples),
        "player": f"0x{PLAYER_OBJECT:08X}",
        "first_ai": f"0x{ai_pointer:08X}",
        "read_only_enforced": True,
        "r4_memory_writes": 0,
        "event_counts": event_counts,
        "comparisons": comparisons,
        "samples": samples,
        "failures": failures,
    }
    report_path = run_dir / "state-pairs.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
