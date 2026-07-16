from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .analysis.mips_branch import MipsBranch, branch_taken, parse_ghidra_branch
from .analysis.visual import analyze_raw_screenshot
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


LOOP_MARKERS = {
    0x8001EB88: "main_loop_start",
    0x8001EC30: "mode_callback",
    0x80114780: "race_overlay",
    0x80038338: "vehicle_dispatcher",
    0x80034178: "camera",
    0x8003C838: "timer",
    0x8004AA7C: "frame_post",
    0x8009331C: "gpu_submit_a",
    0x80093150: "gpu_submit_b",
    0x800930E0: "gpu_submit_c",
}

LOOP_WATCHES = {
    "frame_counter": (0x800ABC94, 4),
    "frame_parity": (0x800F49D0, 4),
    "vsync_threshold": (0x800AC3C4, 4),
    "command_base": (0x800AC9FC, 4),
    "second_submit_enabled": (0x800AC9E0, 4),
    "race_tick": (0x800F2BC4, 4),
    "player_x": (0x800ABCF0, 4),
    "player_y": (0x800ABCF4, 4),
    "player_z": (0x800ABCF8, 4),
    "orientation_x": (0x800ABD30, 4),
    "orientation_y": (0x800ABD34, 4),
    "orientation_z": (0x800ABD38, 4),
    "speed_field": (0x800ABEB8, 2),
    "lap_field": (0x800ABF8A, 2),
    "progress_a": (0x800ABE64, 4),
    "progress_b": (0x800ABE68, 4),
}


def load_branch_inventory(path: Path, executable_sha256: str) -> tuple[MipsBranch, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("protocol_version") != 1:
        raise ValueError("branch inventory must use protocol_version 1")
    if str(value.get("executable_sha256")) != executable_sha256:
        raise ValueError("branch inventory executable identity mismatch")
    raw_branches = value.get("branches")
    if not isinstance(raw_branches, list) or not 1 <= len(raw_branches) <= 6:
        raise ValueError("branch inventory must contain between 1 and 6 bounded branches")
    branches = tuple(parse_ghidra_branch(dict(item)) for item in raw_branches if isinstance(item, dict))
    if len(branches) != len(raw_branches) or len({branch.address for branch in branches}) != len(branches):
        raise ValueError("branch inventory contains invalid or duplicate records")
    return branches


def _read_watches(adapter: PCSXReduxAdapter) -> dict[str, int]:
    return {
        name: int.from_bytes(adapter.read_memory(address, width), "little")
        for name, (address, width) in LOOP_WATCHES.items()
    }


def _branch_event(event: dict[str, Any], branches: dict[int, MipsBranch]) -> dict[str, Any]:
    address = int(event["accessed_address"])
    branch = branches[address]
    registers = {str(name): int(value) for name, value in dict(event.get("gprs", {})).items()}
    taken = branch_taken(branch, registers)
    return {
        "address": f"0x{address:08X}",
        "instruction": branch.mnemonic,
        "previous_instruction": branch.previous_text,
        "delay_slot_address": f"0x{branch.delay_slot_address:08X}",
        "delay_slot": branch.delay_slot_text,
        "target": f"0x{branch.target:08X}",
        "fall_through": f"0x{branch.fall_through:08X}",
        "taken": taken,
        "next_pc": f"0x{branch.target if taken else branch.fall_through:08X}",
        "rs": branch.rs,
        "rs_value": registers.get(branch.rs, 0) if branch.rs != "zero" else 0,
        "rt": branch.rt,
        "rt_value": registers.get(branch.rt, 0) if branch.rt not in {None, "zero"} else 0,
        "pc": f"0x{int(event['pc']):08X}",
        "ra": f"0x{int(event['ra']):08X}",
        "sp": f"0x{int(event['sp']):08X}",
        "cpu_cycles": int(event["cpu_cycles"]),
        "event_vblank": int(event["vblank_index"]),
        "gprs": registers,
    }


def classify_loop_sample(marker_names: list[str], screenshot_changed: bool) -> str:
    active_markers = {"race_overlay", "vehicle_dispatcher", "gpu_submit_a", "frame_post"}
    if active_markers.intersection(marker_names):
        return "active"
    return "duplicate" if not screenshot_changed else "transition_without_active_marker"


def summarize_loop_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    classes = Counter(str(sample["classification"]) for sample in samples)
    marker_counts: Counter[str] = Counter()
    for sample in samples:
        marker_counts.update(str(marker) for marker in sample["markers"])
    branch_counts: dict[str, dict[str, int]] = {}
    for sample in samples:
        for branch in sample["branches"]:
            address = str(branch["address"])
            counts = branch_counts.setdefault(address, {"taken": 0, "not_taken": 0})
            counts["taken" if branch["taken"] else "not_taken"] += 1
    return {
        "class_counts": dict(classes),
        "marker_counts": dict(marker_counts),
        "branch_outcomes": branch_counts,
        "screenshot_transitions": sum(bool(sample["screenshot_changed"]) for sample in samples),
    }


def trace_loop_parity(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    scenario: InputScenario,
    branches: tuple[MipsBranch, ...],
    *,
    vblanks: int = 600,
    max_events: int = 20000,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if vblanks < 120 or vblanks > 600:
        raise ValueError("loop parity VBlanks must be between 120 and 600")
    if max_events < 1024 or max_events > 65536:
        raise ValueError("max_events must be between 1024 and 65536")
    if scenario.vblanks < vblanks:
        raise ValueError("input scenario is shorter than the requested trace")
    if len(branches) + len(LOOP_MARKERS) > 16:
        raise ValueError("branch and marker breakpoint count exceeds 16")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "loop-parity" / stamp
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
            read_only=True,
        ),
        transport,
    )
    branch_map = {branch.address: branch for branch in branches}
    marker_map = dict(LOOP_MARKERS)
    identifiers: list[str] = []
    samples: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []
    failures: list[str] = []
    capture_base = run_dir / "current"
    previous_hash: str | None = None
    try:
        adapter.launch(LaunchConfig("loop-parity", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        adapter.load_state(state)
        adapter.clear_pad_buttons()
        per_breakpoint_limit = min(4096, max(512, vblanks * 4))
        for address in (*branch_map.keys(), *marker_map.keys()):
            identifiers.append(
                adapter.set_breakpoint(BreakpointSpec(address, "execute", 4, per_breakpoint_limit))
            )
        transport.drain_events()
        adapter.set_pad_buttons(list(scenario.buttons))
        for relative_vblank in range(1, vblanks + 1):
            adapter.run_vblanks(1)
            adapter.pause()
            adapter.capture_screenshot(capture_base)
            visual = analyze_raw_screenshot(
                capture_base.with_suffix(".raw"), capture_base.with_suffix(".json")
            )
            interval_events = [event for event in transport.drain_events() if event.get("event") == "breakpoint"]
            raw_events.extend(interval_events)
            if len(raw_events) > max_events:
                raise RuntimeError(f"bounded event limit exceeded: {len(raw_events)} > {max_events}")
            marker_names = [
                marker_map[int(event["accessed_address"])]
                for event in interval_events
                if int(event["accessed_address"]) in marker_map
            ]
            branch_events = [
                _branch_event(event, branch_map)
                for event in interval_events
                if int(event["accessed_address"]) in branch_map
            ]
            changed = previous_hash is not None and visual.sha256 != previous_hash
            samples.append(
                {
                    "relative_vblank": relative_vblank,
                    "emulator_vblank": adapter.get_vblank_count(),
                    "classification": classify_loop_sample(marker_names, changed),
                    "markers": marker_names,
                    "branches": branch_events,
                    "watches": _read_watches(adapter),
                    "screenshot_sha256": visual.sha256,
                    "screenshot_changed": changed,
                    "screenshot_valid": visual.valid_size,
                }
            )
            previous_hash = visual.sha256
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

    with (run_dir / "breakpoints.jsonl").open("w", encoding="utf-8") as handle:
        for event in raw_events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if len(samples) == vblanks and not failures else "FAIL",
        "state_sha256": sha256_file(state),
        "input_sha256": scenario.sha256,
        "scenario": scenario.to_dict(),
        "vblanks": len(samples),
        "read_only_enforced": True,
        "r4_memory_writes": 0,
        "max_events": max_events,
        "event_count": len(raw_events),
        "branches": [branch.__dict__ for branch in branches],
        "summary": summarize_loop_samples(samples),
        "samples": samples,
        "failures": failures,
        "limitations": [
            "PCSX is paused after each VBlank for screenshot/read sampling; interval events are grouped by collection interval.",
            "Branch outcomes are decoded from registers captured at bounded Exec breakpoints.",
            "Only Ghidra-selected branches and fixed evidence-backed globals are observed.",
            "No RAM, scratchpad, disc, BIOS, or save-state write operation is permitted.",
        ],
    }
    report_path = run_dir / "loop-parity.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
