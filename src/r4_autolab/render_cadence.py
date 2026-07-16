from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .analysis.visual import analyze_raw_screenshot
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .input_replay import InputScenario
from .models import LaunchConfig
from .state_capture import CaptureAssets, sha256_file


NTSC_VBLANK_HZ = 59.94


def summarize_render_hashes(hashes: list[str]) -> dict[str, Any]:
    if len(hashes) < 2:
        raise ValueError("at least two render samples are required")
    changes = sum(left != right for left, right in zip(hashes, hashes[1:]))
    intervals = len(hashes) - 1
    return {
        "samples": len(hashes),
        "unique_hashes": len(set(hashes)),
        "changes": changes,
        "duplicate_transition_ratio": 1.0 - changes / intervals,
        "changes_per_vblank": changes / intervals,
        "estimated_change_hz_at_ntsc": changes / intervals * NTSC_VBLANK_HZ,
        "run_lengths": _run_lengths(hashes),
    }


def _run_lengths(hashes: list[str]) -> list[int]:
    lengths: list[int] = []
    current = hashes[0]
    length = 1
    for value in hashes[1:]:
        if value == current:
            length += 1
        else:
            lengths.append(length)
            current = value
            length = 1
    lengths.append(length)
    return lengths


def measure_render_cadence(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    *,
    vblanks: int = 120,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if vblanks < 60 or vblanks > 300:
        raise ValueError("render cadence VBlanks must be between 60 and 300")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "render-cadence" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    capture_base = run_dir / "current"
    scenario = InputScenario(f"accelerate-render-cadence-{vblanks}", vblanks, ("CROSS",))
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
    samples: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        adapter.launch(LaunchConfig("render-cadence", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        adapter.load_state(state)
        adapter.clear_pad_buttons()
        adapter.set_pad_buttons(list(scenario.buttons))
        for relative_vblank in range(vblanks + 1):
            if relative_vblank:
                adapter.run_vblanks(1)
                adapter.pause()
            adapter.capture_screenshot(capture_base)
            visual = analyze_raw_screenshot(
                capture_base.with_suffix(".raw"), capture_base.with_suffix(".json")
            )
            samples.append(
                {
                    "relative_vblank": relative_vblank,
                    "emulator_vblank": adapter.get_vblank_count(),
                    "sha256": visual.sha256,
                    "width": visual.width,
                    "height": visual.height,
                    "bits_per_pixel": visual.bits_per_pixel,
                    "valid_size": visual.valid_size,
                }
            )
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        try:
            adapter.clear_pad_buttons()
        except Exception:
            pass
        try:
            adapter.shutdown()
        except Exception as error:
            failures.append(f"shutdown: {type(error).__name__}: {error}")

    hashes = [str(sample["sha256"]) for sample in samples]
    cadence = summarize_render_hashes(hashes) if len(hashes) >= 2 else None
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if len(samples) == vblanks + 1 and not failures else "FAIL",
        "vblank_intervals": vblanks,
        "state_sha256": sha256_file(state),
        "input_sha256": scenario.sha256,
        "source": "PCSX.GPU.takeScreenShot raw pixels",
        "cadence": cadence,
        "samples": samples,
        "failures": failures,
        "limitations": [
            "Raw screenshot hashes are a fallback because PCSX-Redux exposes no confirmed GPU-command hash API.",
            "A changed screenshot proves a changed displayed image, not which game subsystem produced it.",
            "Capture pauses add wall-clock overhead, so rate is normalized to NTSC VBlank rather than host time.",
            "No memory write or patch was performed.",
        ],
    }
    report_path = run_dir / "render-cadence.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
