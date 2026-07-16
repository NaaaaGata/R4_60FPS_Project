from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Callable, Protocol

from .analysis.iso9660 import PsxExecutableMetadata, cue_bin_path, inspect_disc_executable
from .analysis.observation import R4_STARTING_WATCHES
from .analysis.visual import analyze_raw_screenshot
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter, query_pcsx_redux_version
from .emulator.transport import TcpJsonlTransport
from .models import LaunchConfig, RegisterSnapshot


R4_SERIAL = "SLPS-01800"
R4_EXECUTABLE_SHA256 = "95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775"
MANUAL_PROMPT = """手動操作をお願いします。

1. PCSX-Redux画面でR4を操作してください。
2. レースを開始してください。
3. カウントダウン終了後、直線を走行している安定した地点まで進めてください。
4. 保存したい瞬間に、このターミナルへ戻ってEnterを1回押してください。

ロード画面、暗転中、リスポーン中、ゴール演出中、リプレイ切替中は避けてください。"""


class CaptureAdapter(Protocol):
    def launch(self, config: LaunchConfig) -> object: ...
    def connect(self) -> None: ...
    def handshake(self) -> dict[str, Any]: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def run_vblanks(self, count: int) -> None: ...
    def get_registers(self) -> RegisterSnapshot: ...
    def get_cpu_cycles(self) -> int: ...
    def get_vblank_count(self) -> int: ...
    def read_memory(self, address: int, size: int) -> bytes: ...
    def capture_screenshot(self, path: Path) -> None: ...
    def create_save_state(self, path: Path) -> None: ...
    def load_state(self, path: Path) -> None: ...
    def shutdown(self) -> None: ...


@dataclass(frozen=True)
class CaptureAssets:
    cue: Path
    bin: Path
    bios: Path
    executable: Path
    identity: PsxExecutableMetadata


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    directories = (root, root / "private", root / "input", root / "states", root / "runs")
    found: dict[Path, None] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for suffix in suffixes:
            for path in directory.glob(f"**/*{suffix}"):
                if path.is_file():
                    found[path.resolve()] = None
    return sorted(found)


def _bundled_openbios(pcsx_executable: Path) -> Path | None:
    app_contents = pcsx_executable.parent.parent
    candidate = app_contents / "Resources/share/pcsx-redux/resources/openbios.bin"
    return candidate.resolve() if candidate.is_file() else None


def discover_r4_assets(
    root: Path,
    pcsx_executable: Path,
    *,
    cue_override: Path | None = None,
    bios_override: Path | None = None,
) -> CaptureAssets:
    extraction_directory = root / "private" / "extracted"
    cue_candidates = [cue_override.resolve()] if cue_override is not None else _candidate_files(root, (".cue", ".CUE"))
    selected_cue: Path | None = None
    selected_identity: PsxExecutableMetadata | None = None
    errors: list[str] = []
    for cue in cue_candidates:
        if not cue.is_file():
            errors.append(f"missing CUE: {cue}")
            continue
        try:
            identity = inspect_disc_executable(cue, extraction_directory)
        except (OSError, ValueError) as error:
            errors.append(f"{cue.name}: {error}")
            continue
        if identity.disc_serial == R4_SERIAL and identity.sha256 == R4_EXECUTABLE_SHA256:
            selected_cue = cue
            selected_identity = identity
            break
        errors.append(
            f"{cue.name}: identity mismatch serial={identity.disc_serial} sha256={identity.sha256}"
        )
    if selected_cue is None or selected_identity is None:
        detail = "; ".join(errors) if errors else "no CUE candidates found"
        raise RuntimeError(f"verified R4 Japanese CUE was not found: {detail}")

    selected_bios: Path | None
    if bios_override is not None:
        selected_bios = bios_override.resolve()
        if not selected_bios.is_file():
            raise FileNotFoundError(selected_bios)
    else:
        private_bios = [
            path for path in _candidate_files(root / "private", (".bin", ".rom", ".BIN", ".ROM"))
            if path != cue_bin_path(selected_cue).resolve() and path.stat().st_size == 512 * 1024
        ]
        bundled = _bundled_openbios(pcsx_executable)
        selected_bios = private_bios[0] if private_bios else bundled
        if selected_bios is None:
            raise RuntimeError("no private BIOS or PCSX-Redux bundled OpenBIOS was found")
    return CaptureAssets(
        cue=selected_cue,
        bin=cue_bin_path(selected_cue).resolve(),
        bios=selected_bios,
        executable=Path(selected_identity.extracted_path),
        identity=selected_identity,
    )


def write_asset_report(root: Path, assets: CaptureAssets, pcsx_executable: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = root / "runs" / "environment" / stamp / "assets.json"
    output.parent.mkdir(parents=True, exist_ok=False)
    rawstates = [str(path) for path in _candidate_files(root, (".rawstate",))]
    inputs = [str(path) for path in _candidate_files(root, (".input.json", ".input.toml"))]
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "cue": str(assets.cue),
        "bin": str(assets.bin),
        "bios": str(assets.bios),
        "extracted_executable": str(assets.executable),
        "existing_rawstates": rawstates,
        "input_scripts": inputs,
        "pcsx_redux": str(pcsx_executable),
        "ghidra_analyze_headless": os.environ.get("R4_AUTOLAB_GHIDRA_HEADLESS") or shutil.which("analyzeHeadless"),
        "java": shutil.which("java"),
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _wait_for_file(path: Path, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    previous_size = -1
    stable = 0
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            size = path.stat().st_size
            stable = stable + 1 if size == previous_size else 0
            previous_size = size
            if stable >= 2:
                return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for non-empty stable file: {path}")


def _registers_dict(snapshot: RegisterSnapshot) -> dict[str, Any]:
    return {
        "pc": f"0x{snapshot.pc:08X}",
        "ra": f"0x{snapshot.ra:08X}",
        "sp": f"0x{snapshot.sp:08X}",
        "gprs": {name: f"0x{value:08X}" for name, value in sorted(snapshot.gprs.items())},
    }


def execution_context_matches_target(
    registers: dict[str, Any],
    identity: PsxExecutableMetadata,
) -> bool:
    """Accept target code or a PS1 exception vector returning to target code."""
    pc = int(str(registers["pc"]), 0)
    ra = int(str(registers["ra"]), 0)
    target_start = int(identity.load_address, 0)
    target_end = target_start + identity.payload_size
    pc_in_target = target_start <= pc < target_end
    # Sampling immediately after pause can catch the R3000A general exception
    # vector. In that case RA supplies the interrupted target execution context.
    pc_in_exception_vector = 0x80000000 <= pc < 0x80000100
    ra_in_target = target_start <= ra < target_end
    return pc_in_target or (pc_in_exception_vector and ra_in_target)


def _watch_values(adapter: CaptureAdapter) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for watch in R4_STARTING_WATCHES:
        name = str(watch["name"])
        raw_address = watch["address"]
        raw_width = watch["width"]
        if not isinstance(raw_address, int) or not isinstance(raw_width, int):
            raise TypeError("watch address and width must be integers")
        address = raw_address
        width = raw_width
        data = adapter.read_memory(address, width)
        values[name] = {
            "address": f"0x{address:08X}",
            "width": width,
            "hex": data.hex(),
            "unsigned_le": int.from_bytes(data, "little"),
        }
    return values


def confirm_game_loaded(adapter: CaptureAdapter, identity: PsxExecutableMetadata, timeout_seconds: float) -> RegisterSnapshot:
    load_start = int(identity.load_address, 0)
    load_end = load_start + identity.payload_size
    deadline = time.monotonic() + timeout_seconds
    adapter.pause()
    while time.monotonic() < deadline:
        adapter.run_vblanks(60)
        adapter.pause()
        snapshot = adapter.get_registers()
        if load_start <= snapshot.pc < load_end:
            return snapshot
    raise TimeoutError(
        f"R4 executable did not reach its verified code range 0x{load_start:08X}-0x{load_end:08X}"
    )


def capture_state_artifacts(
    adapter: CaptureAdapter,
    output_directory: Path,
    name: str,
    assets: CaptureAssets,
    pcsx_version: dict[str, str],
    *,
    wait_for_enter: Callable[[], str],
    timeout_seconds: float,
) -> dict[str, Any]:
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
    if not safe_name:
        raise ValueError("state name must contain at least one alphanumeric character")
    state = output_directory / f"{safe_name}.rawstate"
    screenshot = output_directory / safe_name
    cue_before = sha256_file(assets.cue)
    bin_before = sha256_file(assets.bin)

    adapter.resume()
    print(MANUAL_PROMPT, flush=True)
    wait_for_enter()
    adapter.pause()
    registers = adapter.get_registers()
    vblanks = adapter.get_vblank_count()
    cycles = adapter.get_cpu_cycles()
    watches = _watch_values(adapter)
    adapter.capture_screenshot(screenshot)
    adapter.create_save_state(state)
    _wait_for_file(state, timeout_seconds)
    adapter.load_state(state)

    raw_path = screenshot.with_suffix(".raw")
    screenshot_metadata_path = screenshot.with_suffix(".json")
    visual = analyze_raw_screenshot(raw_path, screenshot_metadata_path)
    cue_after = sha256_file(assets.cue)
    bin_after = sha256_file(assets.bin)
    if cue_before != cue_after or bin_before != bin_after:
        raise RuntimeError("source disc identity changed during state capture")
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "state_path": str(state.resolve()),
        "state_size": state.stat().st_size,
        "state_sha256": sha256_file(state),
        "serial": assets.identity.disc_serial,
        "executable_sha256": assets.identity.sha256,
        "disc_sha256": cue_after,
        "bin_sha256": bin_after,
        "bios_sha256": sha256_file(assets.bios),
        "pcsx_redux_changeset": pcsx_version.get("changeset", "unknown"),
        "pc": f"0x{registers.pc:08X}",
        "ra": f"0x{registers.ra:08X}",
        "sp": f"0x{registers.sp:08X}",
        "gprs": _registers_dict(registers)["gprs"],
        "vblank_count": vblanks,
        "cpu_cycles": cycles,
        "screen_width": visual.width,
        "screen_height": visual.height,
        "screen_bits_per_pixel": visual.bits_per_pixel,
        "screenshot_path": str(raw_path.resolve()),
        "screenshot_sha256": visual.sha256,
        "course": "unknown",
        "mode": "unknown",
        "car": "unknown",
        "notes": "Captured after explicit operator Enter; raw protobuf state reloaded once in the capture process.",
        "candidate_values": watches,
        "source_hashes_unchanged": True,
    }
    metadata_path = output_directory / f"{safe_name}.state.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def _validation_sample(adapter: CaptureAdapter, base: Path, advance_vblanks: int) -> dict[str, Any]:
    adapter.pause()
    initial_registers = adapter.get_registers()
    initial = {
        "registers": _registers_dict(initial_registers),
        "vblank_count": adapter.get_vblank_count(),
        "cpu_cycles": adapter.get_cpu_cycles(),
        "candidate_values": _watch_values(adapter),
    }
    adapter.capture_screenshot(base.with_name(base.name + "-initial"))
    initial_visual = analyze_raw_screenshot(
        base.with_name(base.name + "-initial").with_suffix(".raw"),
        base.with_name(base.name + "-initial").with_suffix(".json"),
    )
    adapter.run_vblanks(advance_vblanks)
    adapter.pause()
    final_registers = adapter.get_registers()
    final = {
        "registers": _registers_dict(final_registers),
        "vblank_count": adapter.get_vblank_count(),
        "cpu_cycles": adapter.get_cpu_cycles(),
        "candidate_values": _watch_values(adapter),
    }
    adapter.capture_screenshot(base.with_name(base.name + "-final"))
    final_visual = analyze_raw_screenshot(
        base.with_name(base.name + "-final").with_suffix(".raw"),
        base.with_name(base.name + "-final").with_suffix(".json"),
    )
    initial["screenshot"] = initial_visual.to_dict()
    final["screenshot"] = final_visual.to_dict()
    return {"initial": initial, "after_vblanks": advance_vblanks, "final": final}


def validate_state_reloads(
    root: Path,
    state: Path,
    assets: CaptureAssets,
    pcsx_executable: Path,
    lua_bootstrap: Path,
    timeout_seconds: float,
    *,
    attempts: int = 3,
    advance_vblanks: int = 60,
) -> tuple[Path, dict[str, Any]]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "state-validation" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for index in range(1, attempts + 1):
        attempt_dir = run_dir / f"attempt-{index}"
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
            adapter.launch(LaunchConfig("manual-state-validation", attempt_dir, timeout_seconds))
            adapter.connect()
            handshake = adapter.handshake()
            adapter.pause()
            adapter.load_state(state)
            sample = _validation_sample(adapter, attempt_dir / "capture", advance_vblanks)
            results.append({"attempt": index, "handshake": handshake, **sample})
        except Exception as error:
            failures.append(f"attempt {index}: {type(error).__name__}: {error}")
        finally:
            try:
                adapter.shutdown()
            except Exception as error:
                failures.append(f"attempt {index} shutdown: {type(error).__name__}: {error}")

    status = "FAIL" if failures else "UNKNOWN"
    reasons: list[str] = list(failures)
    if len(results) == attempts:
        initial_values = [item["initial"]["candidate_values"] for item in results]
        final_values = [item["final"]["candidate_values"] for item in results]
        initial_screens = [item["initial"]["screenshot"]["sha256"] for item in results]
        final_screens = [item["final"]["screenshot"]["sha256"] for item in results]
        contexts_in_target = all(
            execution_context_matches_target(item["initial"]["registers"], assets.identity)
            for item in results
        )
        values_equal = all(value == initial_values[0] for value in initial_values[1:])
        trajectory_equal = all(value == final_values[0] for value in final_values[1:])
        screens_equal = len(set(initial_screens)) == 1 and len(set(final_screens)) == 1
        if contexts_in_target and values_equal and trajectory_equal and screens_equal:
            status = "PASS"
        else:
            reasons.extend(
                [
                    f"initial_execution_context_in_target={contexts_in_target}",
                    f"initial_candidate_values_equal={values_equal}",
                    f"post_trajectory_equal={trajectory_equal}",
                    f"screenshot_hashes_equal={screens_equal}",
                ]
            )
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": status,
        "state_path": str(state.resolve()),
        "state_sha256": sha256_file(state),
        "attempts_requested": attempts,
        "attempts_completed": len(results),
        "advance_vblanks": advance_vblanks,
        "results": results,
        "reasons": reasons,
    }
    report_path = run_dir / "validation.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report


def _toml_string(value: str) -> str:
    return json.dumps(value)


def update_project_config(
    path: Path,
    root: Path,
    assets: CaptureAssets,
    state: Path,
    pcsx_executable: Path,
) -> None:
    updates: dict[tuple[str, str], str | int] = {
        ("project", "mode"): "real",
        ("target", "serial"): R4_SERIAL,
        ("target", "executable_sha256"): R4_EXECUTABLE_SHA256,
        ("target", "disc_path"): _portable_path(assets.cue, root),
        ("target", "bios_path"): _portable_path(assets.bios, root),
        ("target", "save_state"): _portable_path(state, root),
        ("emulator", "executable"): _portable_path(pcsx_executable, root),
        ("experiment", "scenario"): "race-straight",
        ("experiment", "vblanks"): 120,
    }
    lines = path.read_text(encoding="utf-8").splitlines()
    section = ""
    replaced: set[tuple[str, str]] = set()
    output: list[str] = []
    for line in lines:
        section_match = re.fullmatch(r"\s*\[([^]]+)]\s*", line)
        if section_match:
            section = section_match.group(1)
            output.append(line)
            continue
        key_match = re.match(r"(\s*)([A-Za-z0-9_]+)\s*=", line)
        key = (section, key_match.group(2)) if key_match else None
        if key is not None and key in updates:
            value = updates[key]
            encoded = str(value) if isinstance(value, int) else _toml_string(value)
            assert key_match is not None
            output.append(f"{key_match.group(1)}{key[1]} = {encoded}")
            replaced.add(key)
        else:
            output.append(line)
    missing = set(updates) - replaced
    if missing:
        raise ValueError("project configuration is missing required keys: " + ", ".join(f"{s}.{k}" for s, k in sorted(missing)))
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _portable_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def run_manual_capture(
    root: Path,
    config_path: Path,
    pcsx_executable: Path,
    lua_bootstrap: Path,
    *,
    name: str,
    cue: Path | None,
    bios: Path | None,
    output_directory: Path | None,
    timeout_seconds: float,
    no_shutdown: bool,
    wait_for_enter: Callable[[], str] = input,
) -> dict[str, Any]:
    assets = discover_r4_assets(root, pcsx_executable, cue_override=cue, bios_override=bios)
    write_asset_report(root, assets, pcsx_executable)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    state_dir = output_directory.resolve() if output_directory else root / "states" / f"manual-race-{stamp}"
    state_dir.mkdir(parents=True, exist_ok=False)
    version = query_pcsx_redux_version(pcsx_executable)
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
            testmode=False,
            portable_directory=state_dir / "portable",
            bios=assets.bios,
            iso=assets.cue,
        ),
        transport,
    )
    metadata: dict[str, Any]
    try:
        adapter.launch(LaunchConfig("manual-race-state-capture", state_dir, timeout_seconds))
        adapter.connect()
        handshake = adapter.handshake()
        if handshake.get("interpreter") is not True or handshake.get("debugger") is not True:
            raise RuntimeError("manual capture requires interpreter and debugger")
        confirm_game_loaded(adapter, assets.identity, timeout_seconds)
        metadata = capture_state_artifacts(
            adapter,
            state_dir,
            name,
            assets,
            version,
            wait_for_enter=wait_for_enter,
            timeout_seconds=timeout_seconds,
        )
    finally:
        if not no_shutdown:
            adapter.shutdown()
    state = Path(str(metadata["state_path"]))
    validation_path: Path | None = None
    validation: dict[str, Any] | None = None
    if not no_shutdown:
        validation_path, validation = validate_state_reloads(
            root,
            state,
            assets,
            pcsx_executable,
            lua_bootstrap,
            timeout_seconds,
        )
    update_project_config(config_path, root, assets, state, pcsx_executable)
    return {
        "state_directory": str(state_dir),
        "state_path": str(state),
        "state_sha256": metadata["state_sha256"],
        "metadata_path": str(state_dir / (re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower() + ".state.json")),
        "validation_path": str(validation_path) if validation_path else None,
        "validation_status": validation["status"] if validation else "SKIP",
        "no_shutdown": no_shutdown,
    }
