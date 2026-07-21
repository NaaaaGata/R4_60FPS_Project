from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from .analysis.gpu import (
    combined_gpu_hash,
    GpuListSnapshot,
    hash_gpu_linked_list,
    parse_display_environment,
    parse_draw_environment,
)
from .analysis.visual import analyze_raw_screenshot
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


GPU_FUNCTIONS = {
    0x8009331C: "put_display_environment",
    0x80093150: "put_draw_environment",
    0x800930E0: "draw_ordering_table",
    0x80034178: "camera_update",
}
COMMAND_ARENA_SIZE = 0x22778
MAX_IPC_READ = 65536


def read_command_arena(adapter: PCSXReduxAdapter, base: int) -> bytes:
    if not 0x80000000 <= base <= 0x80200000 - COMMAND_ARENA_SIZE:
        raise ValueError(f"command arena is outside PS1 RAM: 0x{base:08X}")
    chunks = []
    for offset in range(0, COMMAND_ARENA_SIZE, MAX_IPC_READ):
        size = min(MAX_IPC_READ, COMMAND_ARENA_SIZE - offset)
        chunks.append(adapter.read_memory(base + offset, size))
    data = b"".join(chunks)
    if len(data) != COMMAND_ARENA_SIZE:
        raise ValueError("short command arena read")
    return data


def arena_memory_reader(
    base: int,
    data: bytes,
    fallback: Callable[[int, int], bytes] | None = None,
) -> Callable[[int, int], bytes]:
    def read(address: int, size: int) -> bytes:
        offset = address - base
        if offset < 0 or size < 0 or offset > len(data) - size:
            if fallback is not None:
                return fallback(address, size)
            raise ValueError(
                f"GPU list pointer leaves command arena: address=0x{address:08X} size={size}"
            )
        return data[offset : offset + size]

    return read


def _gpu_event(event: dict[str, Any], order: int) -> dict[str, Any]:
    address = int(event["accessed_address"])
    gprs = dict(event.get("gprs", {}))
    return {
        "order": order,
        "name": GPU_FUNCTIONS[address],
        "address": f"0x{address:08X}",
        "a0": f"0x{int(gprs.get('a0', 0)):08X}",
        "a1": f"0x{int(gprs.get('a1', 0)):08X}",
        "pc": f"0x{int(event['pc']):08X}",
        "ra": f"0x{int(event['ra']):08X}",
        "cpu_cycles": int(event["cpu_cycles"]),
        "event_vblank": int(event["vblank_index"]),
    }


def trace_gpu_buffers(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    scenario: InputScenario,
    *,
    vblanks: int = 240,
    max_nodes: int = 4096,
    max_bytes: int = 1024 * 1024,
    max_events: int = 10000,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if not 120 <= vblanks <= 600:
        raise ValueError("GPU trace VBlanks must be between 120 and 600")
    if scenario.vblanks < vblanks:
        raise ValueError("input scenario is shorter than the requested GPU trace")
    if not 1024 <= max_events <= 65536:
        raise ValueError("max_events must be between 1024 and 65536")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "gpu-buffers" / stamp
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
    identifiers: list[str] = []
    samples: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []
    failures: list[str] = []
    current_display: int | None = None
    current_draw: int | None = None
    current_roots: list[int] = []
    current_lists: list[GpuListSnapshot] = []
    capture_base = run_dir / "current"
    try:
        adapter.launch(LaunchConfig("gpu-buffers", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        adapter.load_state(state)
        adapter.clear_pad_buttons()
        for address in GPU_FUNCTIONS:
            identifiers.append(
                adapter.set_breakpoint(BreakpointSpec(address, "execute", 4, vblanks * 3))
            )
        transport.drain_events()
        adapter.set_pad_buttons(list(scenario.buttons))
        for relative_vblank in range(1, vblanks + 1):
            adapter.run_vblanks(1)
            adapter.pause()
            interval_events = [event for event in transport.drain_events() if event.get("event") == "breakpoint"]
            raw_events.extend(interval_events)
            if len(raw_events) > max_events:
                raise RuntimeError(f"bounded GPU event limit exceeded: {len(raw_events)} > {max_events}")
            ordered_events = [_gpu_event(event, index) for index, event in enumerate(interval_events)]
            roots: list[int] = []
            for event in interval_events:
                address = int(event["accessed_address"])
                a0 = int(dict(event.get("gprs", {})).get("a0", 0))
                if address == 0x8009331C:
                    current_display = a0
                elif address == 0x80093150:
                    current_draw = a0
                elif address == 0x800930E0:
                    roots.append(a0)
            if roots:
                current_roots = roots
            active = bool(roots)

            display = (
                parse_display_environment(adapter.read_memory(current_display, 20))
                if current_display is not None else None
            )
            draw = (
                parse_draw_environment(adapter.read_memory(current_draw, 12))
                if current_draw is not None else None
            )
            if active:
                if current_draw is None:
                    raise RuntimeError("active GPU frame did not provide a command arena base")
                arena = read_command_arena(adapter, current_draw)
                reader = arena_memory_reader(current_draw, arena, adapter.read_memory)
                current_lists = [
                    hash_gpu_linked_list(reader, list_root, max_nodes=max_nodes, max_bytes=max_bytes)
                    for list_root in current_roots
                ]
            lists = current_lists
            adapter.capture_screenshot(capture_base)
            visual = analyze_raw_screenshot(capture_base.with_suffix(".raw"), capture_base.with_suffix(".json"))
            samples.append(
                {
                    "relative_vblank": relative_vblank,
                    "emulator_vblank": adapter.get_vblank_count(),
                    "active_frame": active,
                    "events": ordered_events,
                    "display_buffer_id": display.buffer_id if display else None,
                    "draw_buffer_id": draw.buffer_id if draw else None,
                    "display_environment": asdict(display) if display else None,
                    "draw_environment": asdict(draw) if draw else None,
                    "ordering_table_pointers": [f"0x{value:08X}" for value in current_roots],
                    "gpu_submission_count": len(roots),
                    "gpu_submission_roots": [f"0x{value:08X}" for value in roots],
                    "gpu_lists": [item.to_dict() for item in lists],
                    "gpu_identity_hash": combined_gpu_hash(lists) if lists else None,
                    "gpu_content_hash": combined_gpu_hash(lists, content_only=True) if lists else None,
                    "screenshot_hash": visual.sha256,
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

    active_samples = [sample for sample in samples if sample["active_frame"]]
    duplicate_samples = [sample for sample in samples if not sample["active_frame"]]
    traversal_statuses = sorted({
        str(item["status"])
        for sample in samples
        for item in sample["gpu_lists"]
    })
    ordered_raw = sorted(raw_events, key=lambda event: int(event["cpu_cycles"]))
    camera_cycles = [
        int(event["cpu_cycles"])
        for event in ordered_raw
        if int(event["accessed_address"]) == 0x80034178
    ]
    gpu_start_cycles = [
        int(event["cpu_cycles"])
        for event in ordered_raw
        if int(event["accessed_address"]) == 0x8009331C
    ]
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if len(samples) == vblanks and traversal_statuses == ["terminator"] and not failures else "FAIL",
        "state_sha256": sha256_file(state),
        "input_sha256": scenario.sha256,
        "scenario": scenario.to_dict(),
        "vblanks": len(samples),
        "read_only_enforced": True,
        "r4_memory_writes": 0,
        "bounds": {"max_nodes": max_nodes, "max_bytes": max_bytes, "max_events": max_events},
        "event_count": len(raw_events),
        "summary": {
            "active_frames": len(active_samples),
            "duplicate_frames": len(duplicate_samples),
            "gpu_submissions": sum(int(sample["gpu_submission_count"]) for sample in samples),
            "display_buffer_ids": sorted({str(sample["display_buffer_id"]) for sample in samples}),
            "draw_buffer_ids": sorted({str(sample["draw_buffer_id"]) for sample in samples}),
            "ordering_table_roots": sorted({root for sample in samples for root in sample["ordering_table_pointers"]}),
            "traversal_statuses": traversal_statuses,
            "active_content_hashes": len({str(sample["gpu_content_hash"]) for sample in active_samples}),
            "duplicate_reuses_previous_hash": all(
                index > 0 and samples[index]["gpu_identity_hash"] == samples[index - 1]["gpu_identity_hash"]
                for index in range(len(samples)) if not samples[index]["active_frame"]
            ),
            "camera_has_later_gpu_submission": all(
                any(gpu_cycle > camera_cycle for gpu_cycle in gpu_start_cycles)
                for camera_cycle in camera_cycles[:-1]
            ),
        },
        "official_api": {
            "screenshot": "PCSX.GPU.takeScreenShot()",
            "direct_gpu_status_or_buffer_api": "not documented in the installed/official Lua API; static PsyQ structures and bounded DrawOTag roots used",
        },
        "samples": samples,
        "failures": failures,
    }
    report_path = run_dir / "gpu-buffers.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (run_dir / "breakpoints.jsonl").open("w", encoding="utf-8") as handle:
        for event in raw_events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    return report_path, report
