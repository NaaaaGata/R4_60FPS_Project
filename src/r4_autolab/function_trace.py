from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import BreakpointSpec, LaunchConfig
from .state_capture import CaptureAssets, sha256_file


def summarize_function_hits(events: list[dict[str, Any]], vblanks: int) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[int(event["accessed_address"])].append(event)
    result: list[dict[str, Any]] = []
    for address, hits in sorted(grouped.items()):
        vblank_indices = {int(hit["vblank_index"]) for hit in hits}
        callers = Counter(int(hit["ra"]) for hit in hits)
        result.append(
            {
                "address": f"0x{address:08X}",
                "hits": len(hits),
                "vblanks_with_hits": len(vblank_indices),
                "hits_per_vblank": len(hits) / vblanks,
                "vblank_coverage": len(vblank_indices) / vblanks,
                "callers": [
                    {"ra": f"0x{caller:08X}", "count": count}
                    for caller, count in callers.most_common()
                ],
            }
        )
    return result


def trace_function_cadence(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    addresses: tuple[int, ...],
    *,
    vblanks: int = 120,
    max_hits: int = 256,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if not addresses or len(addresses) > 16:
        raise ValueError("between 1 and 16 function addresses are required")
    if len(set(addresses)) != len(addresses):
        raise ValueError("function addresses must be unique")
    if vblanks <= 0 or vblanks > 600:
        raise ValueError("vblanks must be between 1 and 600")
    if max_hits <= 0 or max_hits > 512:
        raise ValueError("max_hits must be between 1 and 512")
    payload_start = int(assets.identity.load_address, 0)
    payload_end = payload_start + assets.identity.payload_size
    if any(address % 4 or not payload_start <= address < payload_end for address in addresses):
        raise ValueError("all function addresses must be aligned inside the verified payload")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "function-trace" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    scenario = InputScenario(f"accelerate-function-trace-{vblanks}", vblanks, ("CROSS",))
    state_hash = sha256_file(state)
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
    failures: list[str] = []
    hits: list[dict[str, Any]] = []
    try:
        adapter.launch(LaunchConfig("function-cadence", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        adapter.load_state(state)
        adapter.clear_pad_buttons()
        for address in addresses:
            identifiers.append(adapter.set_breakpoint(BreakpointSpec(address, "execute", 4, max_hits)))
        transport.drain_events()
        adapter.set_pad_buttons(list(scenario.buttons))
        adapter.run_vblanks(vblanks)
        adapter.pause()
        adapter.clear_pad_buttons()
        hits = [
            {
                **event,
                "scenario": scenario.name,
                "state_sha256": state_hash,
                "input_sha256": scenario.sha256,
            }
            for event in transport.drain_events()
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
    with (run_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for event in hits:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    summaries = summarize_function_hits(hits, vblanks)
    seen = {summary["address"] for summary in summaries}
    for address in addresses:
        text = f"0x{address:08X}"
        if text not in seen:
            summaries.append(
                {
                    "address": text,
                    "hits": 0,
                    "vblanks_with_hits": 0,
                    "hits_per_vblank": 0.0,
                    "vblank_coverage": 0.0,
                    "callers": [],
                }
            )
    summaries.sort(key=lambda value: str(value["address"]))
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "vblanks": vblanks,
        "max_hits_per_function": max_hits,
        "state_sha256": state_hash,
        "input_sha256": scenario.sha256,
        "read_only_enforced": True,
        "r4_memory_writes": 0,
        "functions": summaries,
        "failures": failures,
        "limitations": [
            "Exec counts reaching max_hits are censored and cannot establish an exact cadence.",
            "Function identities come from Ghidra hypotheses and require dynamic behavior correlation.",
            "No memory write or patch was performed.",
        ],
    }
    report_path = run_dir / "function-trace.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
