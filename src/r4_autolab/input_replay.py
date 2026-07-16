from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from .analysis.observation import R4_STARTING_WATCHES
from .analysis.visual import analyze_raw_screenshot
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .models import LaunchConfig, RegisterSnapshot
from .state_capture import CaptureAssets, sha256_file


ALLOWED_BUTTONS = frozenset(
    {
        "UP", "DOWN", "LEFT", "RIGHT", "CROSS", "CIRCLE", "SQUARE", "TRIANGLE",
        "L1", "L2", "L3", "R1", "R2", "R3", "START", "SELECT",
    }
)


class InputReplayAdapter(Protocol):
    def pause(self) -> None: ...
    def load_state(self, state: Path) -> None: ...
    def set_pad_buttons(self, buttons: list[str]) -> list[str]: ...
    def clear_pad_buttons(self) -> int: ...
    def run_vblanks(self, count: int) -> None: ...
    def get_registers(self) -> RegisterSnapshot: ...
    def get_vblank_count(self) -> int: ...
    def get_cpu_cycles(self) -> int: ...
    def read_memory(self, address: int, size: int) -> bytes: ...
    def capture_screenshot(self, path: Path) -> None: ...


@dataclass(frozen=True)
class InputScenario:
    name: str
    vblanks: int
    buttons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def load_input_scenarios(path: Path) -> dict[str, InputScenario]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("protocol_version") != 1:
        raise ValueError("input scenario file must use protocol_version 1")
    raw_scenarios = value.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("input scenario file must contain a non-empty scenarios array")
    result: dict[str, InputScenario] = {}
    for raw in raw_scenarios:
        if not isinstance(raw, dict):
            raise ValueError("each input scenario must be an object")
        name = str(raw.get("name", ""))
        vblanks = int(raw.get("vblanks", 0))
        raw_buttons = raw.get("buttons", [])
        if not name or name in result:
            raise ValueError(f"duplicate or empty input scenario name: {name!r}")
        if vblanks <= 0 or vblanks > 3600:
            raise ValueError(f"input scenario {name} has an unsafe VBlank count")
        if not isinstance(raw_buttons, list) or any(not isinstance(item, str) for item in raw_buttons):
            raise ValueError(f"input scenario {name} buttons must be strings")
        buttons = tuple(str(item).upper() for item in raw_buttons)
        unknown = sorted(set(buttons) - ALLOWED_BUTTONS)
        if unknown or len(buttons) != len(set(buttons)):
            raise ValueError(f"input scenario {name} has invalid buttons: {unknown or list(buttons)}")
        if {"LEFT", "RIGHT"}.issubset(buttons) or {"UP", "DOWN"}.issubset(buttons):
            raise ValueError(f"input scenario {name} contains contradictory directions")
        result[name] = InputScenario(name, vblanks, buttons)
    return result


def _registers(snapshot: RegisterSnapshot) -> dict[str, Any]:
    return {
        "pc": f"0x{snapshot.pc:08X}",
        "ra": f"0x{snapshot.ra:08X}",
        "sp": f"0x{snapshot.sp:08X}",
        "gprs": {key: f"0x{value:08X}" for key, value in sorted(snapshot.gprs.items())},
    }


def _candidate_values(adapter: InputReplayAdapter) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for watch in R4_STARTING_WATCHES:
        name = watch["name"]
        address = watch["address"]
        width = watch["width"]
        if not isinstance(name, str) or not isinstance(address, int) or not isinstance(width, int):
            raise TypeError("invalid built-in watch")
        data = adapter.read_memory(address, width)
        result[name] = {"hex": data.hex(), "unsigned_le": int.from_bytes(data, "little")}
    return result


def _sample(adapter: InputReplayAdapter, directory: Path, frame: int) -> dict[str, Any]:
    base = directory / f"frame-{frame:04d}"
    adapter.capture_screenshot(base)
    visual = analyze_raw_screenshot(base.with_suffix(".raw"), base.with_suffix(".json"))
    return {
        "relative_vblank": frame,
        "emulator_vblank": adapter.get_vblank_count(),
        "cpu_cycles": adapter.get_cpu_cycles(),
        "registers": _registers(adapter.get_registers()),
        "candidate_values": _candidate_values(adapter),
        "screenshot": visual.to_dict(),
    }


def replay_input_scenario(
    adapter: InputReplayAdapter,
    state: Path,
    scenario: InputScenario,
    output_directory: Path,
    *,
    sample_every: int = 60,
) -> dict[str, Any]:
    if sample_every <= 0 or sample_every > scenario.vblanks:
        raise ValueError("sample_every must be positive and no larger than the scenario")
    output_directory.mkdir(parents=True, exist_ok=False)
    samples: list[dict[str, Any]] = []
    released_count: int | None = None
    active: list[str] = []
    try:
        adapter.pause()
        adapter.load_state(state)
        adapter.clear_pad_buttons()
        samples.append(_sample(adapter, output_directory, 0))
        active = adapter.set_pad_buttons(list(scenario.buttons))
        if active != sorted(scenario.buttons):
            raise RuntimeError(f"pad override acknowledgement mismatch: expected {sorted(scenario.buttons)}, got {active}")
        elapsed = 0
        while elapsed < scenario.vblanks:
            chunk = min(sample_every, scenario.vblanks - elapsed)
            adapter.run_vblanks(chunk)
            adapter.pause()
            elapsed += chunk
            samples.append(_sample(adapter, output_directory, elapsed))
    finally:
        released_count = adapter.clear_pad_buttons()
    report = {
        "scenario": scenario.to_dict(),
        "input_sha256": scenario.sha256,
        "state_sha256": sha256_file(state),
        "sample_every": sample_every,
        "active_buttons_acknowledged": active,
        "released_override_count": released_count,
        "samples": samples,
    }
    (output_directory / "replay.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _signature(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "relative_vblank": sample["relative_vblank"],
            "candidate_values": sample["candidate_values"],
            "screenshot_sha256": sample["screenshot"]["sha256"],
            "screenshot_width": sample["screenshot"]["width"],
            "screenshot_height": sample["screenshot"]["height"],
        }
        for sample in report["samples"]
    ]


def evaluate_replay_attempts(reports: list[dict[str, Any]], attempts: int) -> tuple[str, list[str]]:
    if len(reports) != attempts:
        return "FAIL", [f"completed {len(reports)} of {attempts} attempts"]
    signatures = [_signature(report) for report in reports]
    deterministic = all(signature == signatures[0] for signature in signatures[1:])
    moving = all(
        len({sample["screenshot"]["sha256"] for sample in report["samples"]}) > 1
        for report in reports
    )
    released = all(report["released_override_count"] >= 0 for report in reports)
    reasons = [
        f"deterministic_trajectory={deterministic}",
        f"screen_changed={moving}",
        f"input_release_acknowledged={released}",
    ]
    return ("PASS" if deterministic and moving and released else "FAIL"), reasons


def run_real_input_replays(
    root: Path,
    pcsx_executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    scenarios: list[InputScenario],
    *,
    attempts: int,
    sample_every: int,
    timeout_seconds: float,
) -> tuple[Path, dict[str, Any]]:
    if attempts <= 0 or attempts > 5:
        raise ValueError("attempt count must be between 1 and 5")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "input-replay" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    scenario_results: list[dict[str, Any]] = []
    for scenario in scenarios:
        reports: list[dict[str, Any]] = []
        failures: list[str] = []
        for attempt in range(1, attempts + 1):
            attempt_dir = run_dir / scenario.name / f"attempt-{attempt}"
            transport = TcpJsonlTransport()
            adapter = PCSXReduxAdapter(
                PCSXLaunchOptions(
                    executable=pcsx_executable,
                    lua_bootstrap=lua_bootstrap,
                    run=True,
                    stdout=True,
                    lua_stdout=True,
                    interpreter=True,
                    debugger=True,
                    testmode=True,
                    portable_directory=attempt_dir / "portable",
                    bios=assets.bios,
                    iso=assets.cue,
                ),
                transport,
            )
            try:
                adapter.launch(LaunchConfig(scenario.name, attempt_dir, timeout_seconds))
                adapter.connect()
                adapter.handshake()
                reports.append(
                    replay_input_scenario(
                        adapter,
                        state,
                        scenario,
                        attempt_dir / "samples",
                        sample_every=sample_every,
                    )
                )
            except Exception as error:
                failures.append(f"attempt {attempt}: {type(error).__name__}: {error}")
            finally:
                try:
                    adapter.clear_pad_buttons()
                except Exception:
                    pass
                try:
                    adapter.shutdown()
                except Exception as error:
                    failures.append(f"attempt {attempt} shutdown: {type(error).__name__}: {error}")
        status, reasons = evaluate_replay_attempts(reports, attempts)
        if failures:
            status = "FAIL"
            reasons.extend(failures)
        scenario_results.append(
            {
                "name": scenario.name,
                "input_sha256": scenario.sha256,
                "status": status,
                "reasons": reasons,
                "attempts": len(reports),
                "reports": reports,
            }
        )
    overall = "PASS" if all(result["status"] == "PASS" for result in scenario_results) else "FAIL"
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": overall,
        "state_path": str(state.resolve()),
        "state_sha256": sha256_file(state),
        "attempts_per_scenario": attempts,
        "sample_every": sample_every,
        "scenarios": scenario_results,
    }
    report_path = run_dir / "input-replay.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
