from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


@dataclass(frozen=True)
class FunctionEvidence:
    name: str
    role: str
    side_effects: tuple[str, ...]
    evidence: str
    confidence: str


FUNCTION_EVIDENCE = {
    0x80114780: FunctionEvidence("race_overlay", "logic-only", ("timer", "player", "AI", "static", "ordering-table"), "overlay decompilation dispatches the complete active race frame", "high"),
    0x8003C838: FunctionEvidence("lap_timer", "timer", ("timer", "player", "static"), "writes lap counters, lap field, results, and race-mode globals", "high"),
    0x8002C158: FunctionEvidence("hud_begin", "HUD-build", ("scratch", "ordering-table"), "reads lap timing and appends 0x14-byte primitives from command arena", "medium-high"),
    0x80020E54: FunctionEvidence("hud_end", "HUD-build", ("scratch", "ordering-table"), "selects command arena roots and appends primitives", "medium-high"),
    0x80038338: FunctionEvidence("vehicle_dispatcher", "AI", ("player", "AI", "scratch", "static"), "iterates 0x800FFA00 and calls vehicle physics phases", "high"),
    0x80034178: FunctionEvidence("camera_update", "camera", ("scratch", "static"), "builds camera transform state from player transform", "high"),
    0x8007346C: FunctionEvidence("world_animation_update", "animation", ("animation", "RNG", "audio", "scratch", "static"), "updates runtime world/effect objects and may emit sound", "medium-high"),
    0x8006E078: FunctionEvidence("camera_matrix_complete", "render-state-build", ("scratch", "static"), "builds view matrices from camera scratch state", "medium-high"),
    0x8002E808: FunctionEvidence("render_phase_a", "unknown", ("static",), "dynamically selected overlay phase; semantics not yet uniquely named", "low"),
    0x8006EBB4: FunctionEvidence("render_phase_b", "geometry-transform", ("scratch", "static", "ordering-table"), "called after camera matrices and before later world phases", "medium"),
    0x80074680: FunctionEvidence("world_geometry_effects", "geometry-transform", ("animation", "audio", "RNG", "scratch", "static", "ordering-table"), "large world/effect transform routine mutates effect state and emits primitives", "medium-high"),
    0x80037584: FunctionEvidence("camera_track_lookup", "render-state-build", ("scratch", "static"), "uses completed camera position for track/camera lookup", "medium"),
    0x80070600: FunctionEvidence("hud_animation", "HUD-build", ("animation", "scratch", "static", "ordering-table"), "updates HUD transition state and appends a primitive", "medium-high"),
    0x80050368: FunctionEvidence("frame_audio_state", "animation", ("audio", "static"), "stores two frame parameters in indexed static audio/game state", "medium"),
    0x8009331C: FunctionEvidence("gpu_submission_start", "GPU-submit-preparation", ("GPU", "static"), "PutDispEnv-equivalent first GPU call after overlay return", "high"),
}


UNSAFE_RENDER_EFFECTS = frozenset({
    "timer", "player", "AI", "RNG", "audio", "animation", "static",
    "frame-counter", "replay", "CD", "heap",
})


def render_only_eligible(evidence: FunctionEvidence) -> bool:
    return not UNSAFE_RENDER_EFFECTS.intersection(evidence.side_effects)


def reconstruct_call_order(
    events: list[dict[str, Any]],
    *,
    requested_frames: int,
    max_events_per_frame: int,
) -> list[dict[str, Any]]:
    if requested_frames <= 0:
        raise ValueError("requested_frames must be positive")
    if not 16 <= max_events_per_frame <= 2048:
        raise ValueError("max_events_per_frame must be between 16 and 2048")
    ordered = sorted(events, key=lambda event: int(event["cpu_cycles"]))
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] | None = None
    for event in ordered:
        address = int(event["accessed_address"])
        if address == 0x80114780:
            if current is not None:
                groups.append(current)
            current = []
        if current is not None:
            current.append(event)
    if current:
        groups.append(current)
    groups = groups[:requested_frames]
    result: list[dict[str, Any]] = []
    for frame_index, group in enumerate(groups, start=1):
        if len(group) > max_events_per_frame:
            raise RuntimeError(
                f"frame {frame_index} exceeded event bound: {len(group)} > {max_events_per_frame}"
            )
        sequence = []
        for sequence_number, event in enumerate(group, start=1):
            address = int(event["accessed_address"])
            evidence = FUNCTION_EVIDENCE[address]
            ra = int(event["ra"])
            sequence.append(
                {
                    "sequence_number": sequence_number,
                    "vblank": int(event["vblank_index"]),
                    "cpu_cycle": int(event["cpu_cycles"]),
                    "pc": f"0x{int(event['pc']):08X}",
                    "address": f"0x{address:08X}",
                    "function": evidence.name,
                    "caller": None if address == 0x80114780 else f"0x{(ra - 8) & 0xFFFFFFFF:08X}",
                    "ra": f"0x{ra:08X}",
                    "depth_estimate": 0 if address == 0x80114780 else 1,
                    "role_candidate": evidence.role,
                    "side_effect_classification": list(evidence.side_effects),
                    "render_only_eligible": render_only_eligible(evidence),
                    "evidence": evidence.evidence,
                    "confidence": evidence.confidence,
                }
            )
        result.append({"active_frame": frame_index, "sequence": sequence})
    return result


def trace_race_call_order(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    scenario: InputScenario,
    *,
    frames: int = 30,
    max_events_per_frame: int = 2048,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if not 1 <= frames <= 120:
        raise ValueError("frames must be between 1 and 120")
    required_vblanks = frames * 2 + 4
    if scenario.vblanks < required_vblanks:
        raise ValueError("input scenario is shorter than the requested call-order trace")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "race-call-order" / stamp
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
    events: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        adapter.launch(LaunchConfig("race-call-order", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        adapter.load_state(state)
        adapter.clear_pad_buttons()
        max_hits = max(64, frames * 4)
        for address in FUNCTION_EVIDENCE:
            identifiers.append(adapter.set_breakpoint(BreakpointSpec(address, "execute", 4, max_hits)))
        transport.drain_events()
        adapter.set_pad_buttons(list(scenario.buttons))
        adapter.run_vblanks(required_vblanks)
        adapter.pause()
        events = [event for event in transport.drain_events() if event.get("event") == "breakpoint"]
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

    reconstructed: list[dict[str, Any]] = []
    try:
        reconstructed = reconstruct_call_order(
            events, requested_frames=frames, max_events_per_frame=max_events_per_frame
        )
    except (ValueError, RuntimeError) as error:
        failures.append(f"reconstruction: {type(error).__name__}: {error}")
    role_counts: dict[str, int] = {}
    for frame in reconstructed:
        for event in frame["sequence"]:
            role = str(event["role_candidate"])
            role_counts[role] = role_counts.get(role, 0) + 1
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if len(reconstructed) == frames and not failures else "FAIL",
        "state_sha256": sha256_file(state),
        "input_sha256": scenario.sha256,
        "scenario": scenario.to_dict(),
        "requested_frames": frames,
        "completed_frames": len(reconstructed),
        "max_events_per_frame": max_events_per_frame,
        "breakpoint_count": len(FUNCTION_EVIDENCE),
        "event_count": len(events),
        "read_only_enforced": True,
        "r4_memory_writes": 0,
        "function_evidence": {
            f"0x{address:08X}": asdict(evidence) | {"render_only_eligible": render_only_eligible(evidence)}
            for address, evidence in FUNCTION_EVIDENCE.items()
        },
        "role_counts": role_counts,
        "frames": reconstructed,
        "failures": failures,
        "limitations": [
            "Depth is a selected-boundary estimate, not a full stack unwind.",
            "Only 15 statically selected functions are traced; unknown callees are not relabelled.",
            "Side effects are bounded static classifications for dynamically reached functions.",
        ],
    }
    report_path = run_dir / "call-order.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
