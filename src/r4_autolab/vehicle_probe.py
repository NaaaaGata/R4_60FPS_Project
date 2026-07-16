from __future__ import annotations

from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import Any

from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


PLAYER_POINTER_TABLE = 0x800FFA00
PLAYER_OBJECT = 0x800ABCE0
PLAYER_OBJECT_SIZE = 0x400
INPUT_BITFIELD = 0x800F3820
ENGINE_GAUGE_VALUE = 0x800F4A50
SPEED_OFFSET = 0x1D8
GEAR_CANDIDATE_OFFSET = 0x27A


def pearson(values_a: list[int], values_b: list[int]) -> float | None:
    if len(values_a) != len(values_b) or len(values_a) < 3:
        return None
    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    variance_a = sum((value - mean_a) ** 2 for value in values_a)
    variance_b = sum((value - mean_b) ** 2 for value in values_b)
    if variance_a == 0 or variance_b == 0:
        return None
    covariance = sum((a - mean_a) * (b - mean_b) for a, b in zip(values_a, values_b, strict=True))
    return covariance / math.sqrt(variance_a * variance_b)


def rank_object_fields(samples: list[bytes], *, limit: int = 24) -> list[dict[str, Any]]:
    if not samples or any(len(sample) != PLAYER_OBJECT_SIZE for sample in samples):
        raise ValueError("all player object samples must be exactly 0x400 bytes")
    if not 1 <= limit <= 64:
        raise ValueError("field result limit must be between 1 and 64")
    speed = [int.from_bytes(sample[SPEED_OFFSET:SPEED_OFFSET + 2], "little") for sample in samples]
    ranked: list[dict[str, Any]] = []
    for width in (2, 4):
        for offset in range(0, PLAYER_OBJECT_SIZE - width + 1, width):
            values = [int.from_bytes(sample[offset:offset + width], "little") for sample in samples]
            unique = len(set(values))
            if unique < 2:
                continue
            correlation = pearson(values, speed)
            ranked.append(
                {
                    "offset": f"0x{offset:03X}",
                    "address": f"0x{PLAYER_OBJECT + offset:08X}",
                    "width": width,
                    "unique_values": unique,
                    "min": min(values),
                    "max": max(values),
                    "speed_correlation": correlation,
                }
            )
    ranked.sort(
        key=lambda item: (
            abs(float(item["speed_correlation"])) if item["speed_correlation"] is not None else -1.0,
            int(item["unique_values"]),
        ),
        reverse=True,
    )
    return ranked[:limit]


def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "access": event["access"],
        "pc": f"0x{int(event['pc']):08X}",
        "ra": f"0x{int(event['ra']):08X}",
        "address": f"0x{int(event['accessed_address']):08X}",
        "width": int(event["access_width"]),
        "vblank": int(event["vblank_index"]),
        "cpu_cycles": int(event["cpu_cycles"]),
    }


def trace_input_and_engine_state(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    scenarios: list[InputScenario],
    *,
    vblanks: int = 120,
    sample_every: int = 2,
    max_hits: int = 64,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if not 8 <= vblanks <= 600 or sample_every <= 0 or vblanks % sample_every:
        raise ValueError("invalid bounded input/engine sampling interval")
    if not 1 <= max_hits <= 256:
        raise ValueError("max_hits must be between 1 and 256")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "input-engine" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    scenario_reports: list[dict[str, Any]] = []
    failures: list[str] = []
    for scenario in scenarios:
        if scenario.vblanks < vblanks:
            raise ValueError(f"scenario {scenario.name} is shorter than requested sampling")
        transport = TcpJsonlTransport()
        adapter = PCSXReduxAdapter(
            PCSXLaunchOptions(
                executable=executable, lua_bootstrap=lua_bootstrap,
                run=True, stdout=True, lua_stdout=True, interpreter=True, debugger=True, testmode=True,
                portable_directory=run_dir / f"portable-{scenario.name}",
                bios=assets.bios, iso=assets.cue, read_only=True,
            ),
            transport,
        )
        identifiers: list[str] = []
        samples: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        try:
            adapter.launch(LaunchConfig(f"input-engine-{scenario.name}", run_dir, timeout_seconds))
            adapter.connect()
            adapter.handshake()
            adapter.pause()
            adapter.load_state(state)
            pointer = int.from_bytes(adapter.read_memory(PLAYER_POINTER_TABLE, 4), "little")
            if pointer != PLAYER_OBJECT:
                raise RuntimeError(f"player pointer identity mismatch: 0x{pointer:08X}")
            adapter.clear_pad_buttons()
            for spec in (
                BreakpointSpec(INPUT_BITFIELD, "write", 4, max_hits),
                BreakpointSpec(ENGINE_GAUGE_VALUE, "write", 2, max_hits),
                BreakpointSpec(ENGINE_GAUGE_VALUE, "read", 2, max_hits),
                BreakpointSpec(0x8004AA7C, "execute", 4, max_hits),
                BreakpointSpec(0x80114780, "execute", 4, max_hits),
                BreakpointSpec(0x80038338, "execute", 4, max_hits),
            ):
                identifiers.append(adapter.set_breakpoint(spec))
            transport.drain_events()
            adapter.set_pad_buttons(list(scenario.buttons))
            elapsed = 0
            while elapsed < vblanks:
                adapter.run_vblanks(sample_every)
                adapter.pause()
                elapsed += sample_every
                interval = [event for event in transport.drain_events() if event.get("event") == "breakpoint"]
                events.extend(interval)
                object_data = adapter.read_memory(PLAYER_OBJECT, PLAYER_OBJECT_SIZE)
                samples.append(
                    {
                        "relative_vblank": elapsed,
                        "input_bitfield": int.from_bytes(adapter.read_memory(INPUT_BITFIELD, 4), "little"),
                        "engine_gauge_value": int.from_bytes(adapter.read_memory(ENGINE_GAUGE_VALUE, 2), "little"),
                        "speed_related": int.from_bytes(object_data[SPEED_OFFSET:SPEED_OFFSET + 2], "little"),
                        "gear_candidate": int.from_bytes(object_data[GEAR_CANDIDATE_OFFSET:GEAR_CANDIDATE_OFFSET + 2], "little"),
                        "object_hex": object_data.hex(),
                    }
                )
        except Exception as error:
            failures.append(f"{scenario.name}: {type(error).__name__}: {error}")
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
                failures.append(f"{scenario.name} shutdown: {type(error).__name__}: {error}")
        object_samples = [bytes.fromhex(str(sample["object_hex"])) for sample in samples]
        for sample in samples:
            sample.pop("object_hex", None)
        scenario_reports.append(
            {
                "scenario": scenario.to_dict(),
                "input_sha256": scenario.sha256,
                "samples": samples,
                "ranked_object_fields": rank_object_fields(object_samples) if object_samples else [],
                "events": [_event_summary(event) for event in events],
            }
        )
    input_values = {
        report["scenario"]["name"]: sorted({sample["input_bitfield"] for sample in report["samples"]})
        for report in scenario_reports
    }
    engine_write_pcs = sorted({
        event["pc"] for report in scenario_reports for event in report["events"]
        if event["address"] == f"0x{ENGINE_GAUGE_VALUE:08X}" and event["access"] == "write"
    })
    engine_read_pcs = sorted({
        event["pc"] for report in scenario_reports for event in report["events"]
        if event["address"] == f"0x{ENGINE_GAUGE_VALUE:08X}" and event["access"] == "read"
    })
    input_write_pcs = sorted({
        event["pc"] for report in scenario_reports for event in report["events"]
        if int(str(event["address"]), 0) in {INPUT_BITFIELD, INPUT_BITFIELD + 2}
        and event["access"] == "write"
    })
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if all(len(item["samples"]) == vblanks // sample_every for item in scenario_reports) and not failures else "FAIL",
        "state_sha256": sha256_file(state),
        "vblanks_per_scenario": vblanks,
        "sample_every": sample_every,
        "player_object": f"0x{PLAYER_OBJECT:08X}",
        "object_window_bytes": PLAYER_OBJECT_SIZE,
        "read_only_enforced": True,
        "r4_memory_writes": 0,
        "input": {
            "bitfield_address": f"0x{INPUT_BITFIELD:08X}",
            "values_by_scenario": input_values,
            "bounded_write_pcs": input_write_pcs,
        },
        "engine": {
            "hud_gauge_address": f"0x{ENGINE_GAUGE_VALUE:08X}",
            "bounded_write_pcs": engine_write_pcs,
            "bounded_read_pcs": engine_read_pcs,
            "classification": "engine-speed-related candidate; RPM scale not proven",
        },
        "scenarios": scenario_reports,
        "failures": failures,
    }
    report_path = run_dir / "input-engine.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
