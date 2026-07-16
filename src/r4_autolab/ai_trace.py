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


ACTIVE_VEHICLE_COUNT = 0x800AC384
VEHICLE_POINTER_TABLE = 0x800FFA00
PLAYER_OBJECT = 0x800ABCE0
VEHICLE_READ_START = 0x10
VEHICLE_READ_END = 0x2AC


def validate_vehicle_pointers(count: int, pointers: list[int]) -> None:
    if not 2 <= count <= 16:
        raise ValueError(f"active vehicle count is outside 2..16: {count}")
    if len(pointers) != count:
        raise ValueError("vehicle pointer count mismatch")
    if pointers[0] != PLAYER_OBJECT:
        raise ValueError(f"first vehicle is not the verified player object: 0x{pointers[0]:08X}")
    if len(set(pointers)) != len(pointers):
        raise ValueError("vehicle pointer table contains duplicates")
    for pointer in pointers:
        if pointer % 4 or not 0x80010000 <= pointer <= 0x80200000 - VEHICLE_READ_END:
            raise ValueError(f"invalid vehicle object pointer: 0x{pointer:08X}")


def decode_vehicle(pointer: int, data: bytes) -> dict[str, Any]:
    expected = VEHICLE_READ_END - VEHICLE_READ_START
    if len(data) != expected:
        raise ValueError(f"vehicle field window must be exactly {expected} bytes")

    def unsigned(offset: int, width: int) -> int:
        start = offset - VEHICLE_READ_START
        return int.from_bytes(data[start:start + width], "little")

    def signed(offset: int, width: int) -> int:
        start = offset - VEHICLE_READ_START
        return int.from_bytes(data[start:start + width], "little", signed=True)

    return {
        "pointer": f"0x{pointer:08X}",
        "x": signed(0x10, 4), "y": signed(0x14, 4), "z": signed(0x18, 4),
        "orientation_x": signed(0x50, 4),
        "orientation_y": signed(0x54, 4),
        "orientation_z": signed(0x58, 4),
        "speed_related": unsigned(0x1D8, 2),
        "rank": signed(0x1EE, 2),
        "progress_a": signed(0x184, 4),
        "progress_b": signed(0x188, 4),
    }


def trajectory_signature(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"relative_vblank": sample["relative_vblank"], "vehicles": sample["vehicles"]}
        for sample in samples
    ]


def _field_changes(samples: list[dict[str, Any]], vehicle_index: int, field: str) -> int:
    values = [sample["vehicles"][vehicle_index][field] for sample in samples]
    return sum(current != previous for previous, current in zip(values, values[1:]))


def trace_ai_trajectories(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    scenario: InputScenario,
    *,
    attempts: int = 3,
    vblanks: int = 600,
    sample_every: int = 2,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if attempts != 3:
        raise ValueError("AI trajectory verification requires exactly 3 attempts")
    if not 120 <= vblanks <= 600 or sample_every != 2:
        raise ValueError("AI trace requires 120..600 VBlanks sampled every 2")
    if scenario.vblanks < vblanks:
        raise ValueError("input scenario is shorter than the requested AI trace")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "ai-trajectories" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    attempt_reports: list[dict[str, Any]] = []
    failures: list[str] = []
    for attempt in range(1, attempts + 1):
        transport = TcpJsonlTransport()
        adapter = PCSXReduxAdapter(
            PCSXLaunchOptions(
                executable=executable, lua_bootstrap=lua_bootstrap,
                run=True, stdout=True, lua_stdout=True, interpreter=True, debugger=True, testmode=True,
                portable_directory=run_dir / f"portable-{attempt}",
                bios=assets.bios, iso=assets.cue, read_only=True,
            ),
            transport,
        )
        identifier: str | None = None
        samples: list[dict[str, Any]] = []
        dispatcher_events: list[dict[str, Any]] = []
        pointers: list[int] = []
        count = 0
        try:
            adapter.launch(LaunchConfig(f"ai-trajectories-{attempt}", run_dir, timeout_seconds))
            adapter.connect()
            adapter.handshake()
            adapter.pause()
            adapter.load_state(state)
            adapter.clear_pad_buttons()
            count = int.from_bytes(adapter.read_memory(ACTIVE_VEHICLE_COUNT, 4), "little")
            pointer_data = adapter.read_memory(VEHICLE_POINTER_TABLE, count * 4)
            pointers = [int.from_bytes(pointer_data[index * 4:index * 4 + 4], "little") for index in range(count)]
            validate_vehicle_pointers(count, pointers)
            identifier = adapter.set_breakpoint(BreakpointSpec(0x80038338, "execute", 4, vblanks))
            transport.drain_events()
            adapter.set_pad_buttons(list(scenario.buttons))
            elapsed = 0
            while elapsed < vblanks:
                adapter.run_vblanks(sample_every)
                adapter.pause()
                elapsed += sample_every
                dispatcher_events.extend(
                    event for event in transport.drain_events()
                    if event.get("event") == "breakpoint"
                )
                vehicles = [
                    decode_vehicle(
                        pointer,
                        adapter.read_memory(
                            pointer + VEHICLE_READ_START,
                            VEHICLE_READ_END - VEHICLE_READ_START,
                        ),
                    )
                    for pointer in pointers
                ]
                samples.append({"relative_vblank": elapsed, "vehicles": vehicles})
        except Exception as error:
            failures.append(f"attempt {attempt}: {type(error).__name__}: {error}")
        finally:
            if identifier is not None:
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
                failures.append(f"attempt {attempt} shutdown: {type(error).__name__}: {error}")
        attempt_reports.append(
            {
                "attempt": attempt,
                "active_count": count,
                "pointers": [f"0x{pointer:08X}" for pointer in pointers],
                "dispatcher_hits": len(dispatcher_events),
                "samples": samples,
            }
        )
    signatures = [trajectory_signature(report["samples"]) for report in attempt_reports]
    deterministic = len(signatures) == attempts and all(signature == signatures[0] for signature in signatures[1:])
    first_samples = attempt_reports[0]["samples"] if attempt_reports else []
    vehicle_summaries: list[dict[str, Any]] = []
    if first_samples:
        for index, pointer in enumerate(attempt_reports[0]["pointers"]):
            vehicle_summaries.append(
                {
                    "index": index,
                    "kind": "player" if index == 0 else "AI",
                    "pointer": pointer,
                    "x_changes": _field_changes(first_samples, index, "x"),
                    "y_changes": _field_changes(first_samples, index, "y"),
                    "z_changes": _field_changes(first_samples, index, "z"),
                    "orientation_changes": _field_changes(first_samples, index, "orientation_y"),
                    "speed_changes": _field_changes(first_samples, index, "speed_related"),
                    "rank_values": sorted({sample["vehicles"][index]["rank"] for sample in first_samples}),
                    "progress_changes": _field_changes(first_samples, index, "progress_b"),
                    "update_cadence": "30 Hz dispatcher; field change count is value-dependent",
                }
            )
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if deterministic and all(len(item["samples"]) == vblanks // 2 for item in attempt_reports) and not failures else "FAIL",
        "state_sha256": sha256_file(state),
        "input_sha256": scenario.sha256,
        "scenario": scenario.to_dict(),
        "attempts": attempts,
        "vblanks": vblanks,
        "sample_every": sample_every,
        "deterministic": deterministic,
        "read_only_enforced": True,
        "r4_memory_writes": 0,
        "vehicle_summaries": vehicle_summaries,
        "attempt_reports": attempt_reports,
        "failures": failures,
    }
    report_path = run_dir / "ai-trajectories.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
