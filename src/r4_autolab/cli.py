from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tomllib
from typing import Any, Sequence

from . import __version__
from .config import ProjectConfig, load_project_config
from .emulator.fake import FakeEmulator
from .emulator.capabilities import CapabilityCheck, CapabilityReport, CapabilityRunner
from .emulator.pcsx_redux import (
    PCSXLaunchOptions,
    PCSXReduxAdapter,
    discover_pcsx_redux,
    local_architecture,
    query_pcsx_redux_version,
)
from .emulator.transport import TcpJsonlTransport
from .evaluator import compare_summaries, evaluate_trace_pair, load_jsonl, summary_from_record, summarize_events
from .analysis.visual import analyze_raw_screenshot
from .analysis.iso9660 import inspect_disc_executable
from .analysis.observation import observe_r4_boot
from .models import ExperimentProposal, TargetVersion
from .reporting.markdown import render_run_report
from .storage import ExperimentStore
from .supervisor import ExperimentSupervisor
from .ghidra.exports import load_static_export
from .ghidra.runner import (
    FakeGhidraRunner,
    GhidraHeadlessRunner,
    GhidraRunConfig,
    cache_key,
    discover_analyze_headless,
)
from .campaign import CampaignBudget, CampaignRunner, ProposalCampaignRunner
from .codex_client import CodexExecClient, FakeCodexClient, discover_codex, verify_codex_executable
from .state_capture import discover_r4_assets, run_manual_capture
from .input_replay import load_input_scenarios, run_real_input_replays
from .race_trace import trace_r4_race
from .function_trace import trace_function_cadence
from .overlay_probe import probe_runtime_overlay
from .targeted_trace import parse_target_watch, trace_targeted_addresses
from .render_cadence import measure_render_cadence
from .scratch_audit import audit_scratch_location
from .loop_parity import load_branch_inventory, trace_loop_parity
from .gpu_trace import trace_gpu_buffers
from .call_order import trace_race_call_order
from .vehicle_probe import trace_input_and_engine_state
from .ai_trace import trace_ai_trajectories


FAKE_TARGET = TargetVersion("FAKE", "0" * 64)


def _timestamp_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"


def _target(config: ProjectConfig) -> TargetVersion:
    if config.mode == "fake":
        return FAKE_TARGET
    return TargetVersion(config.serial, config.executable_sha256)


def _supervisor(config: ProjectConfig, store: ExperimentStore) -> ExperimentSupervisor:
    if config.mode == "fake":
        emulator: Any = FakeEmulator()
    else:
        executable = discover_pcsx_redux(config.pcsx_executable)
        if executable is None:
            raise RuntimeError("real mode requires an installed PCSX-Redux executable")
        if config.disc_path is None or not config.disc_path.is_file():
            raise RuntimeError("real mode requires an explicit private target.disc_path")
        emulator = PCSXReduxAdapter(
            PCSXLaunchOptions(
                executable=executable,
                lua_bootstrap=config.lua_bootstrap.resolve(),
                run=True,
                stdout=True,
                lua_stdout=True,
                interpreter=True,
                debugger=True,
                testmode=True,
                bios=config.bios_path,
                iso=config.disc_path,
            ),
            TcpJsonlTransport(),
        )
    return ExperimentSupervisor(store, emulator, config.runs_dir, _target(config), timeout_seconds=config.timeout_seconds)


def _load_config(args: argparse.Namespace) -> ProjectConfig:
    path = Path(args.config)
    if not path.exists():
        raise FileNotFoundError(f"configuration not found: {path}; run r4-autolab init-config")
    return load_project_config(path)


def command_doctor(args: argparse.Namespace) -> int:
    python_ok = sys.version_info >= (3, 11)
    pcsx_path = discover_pcsx_redux()
    configured_ghidra: Path | None = None
    config_path = Path(args.config)
    if config_path.is_file():
        configured_ghidra = load_project_config(config_path).ghidra_headless
    ghidra_path = discover_analyze_headless(configured_ghidra)
    pcsx_version: str | None = None
    if pcsx_path is not None:
        try:
            version_info = query_pcsx_redux_version(pcsx_path)
            pcsx_version = version_info.get("changeset") or version_info.get("version")
        except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
            pcsx_version = "detected; version query failed"
    tools = [
        ("Python >= 3.11", sys.executable, sys.version.split()[0], True, python_ok),
        ("Git", shutil.which("git"), None, False, True),
        ("Codex CLI", os.environ.get("R4_AUTOLAB_CODEX") or shutil.which("codex"), None, False, True),
        ("PCSX-Redux", str(pcsx_path) if pcsx_path else None, pcsx_version, False, True),
        ("Ghidra analyzeHeadless", str(ghidra_path) if ghidra_path else None, None, False, True),
        ("Java", shutil.which("java"), None, False, True),
    ]
    print(f"R4 AutoLab {__version__}")
    for name, path, tool_version, required, valid in tools:
        status = "OK" if path and valid else ("MISSING" if required else "optional-missing")
        detail = f" ({tool_version})" if tool_version else ""
        print(f"{status:16} {'required' if required else 'optional':8} {name}: {path or '-'}{detail}")
    return 0 if python_ok else 1


def _write_unavailable_capability_report(
    run_dir: Path,
    detail: str,
) -> CapabilityReport:
    run_dir.mkdir(parents=True, exist_ok=False)
    report = CapabilityReport(
        created_at=datetime.now(UTC).isoformat(),
        executable="",
        version={},
        architecture=local_architecture(),
        checks=[CapabilityCheck("launch", "FAIL", detail)],
        log_path=str(run_dir / "pcsx-redux.log"),
    )
    (run_dir / "capabilities.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def command_pcsx_capabilities(args: argparse.Namespace) -> int:
    config = _load_config(args)
    run_dir = config.runs_dir / "capabilities" / _timestamp_id("pcsx")
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        report = _write_unavailable_capability_report(
            run_dir,
            "PCSX-Redux executable not found via environment, configuration, PATH, or macOS application directories",
        )
    else:
        version_info = query_pcsx_redux_version(executable)
        transport = TcpJsonlTransport()
        options = PCSXLaunchOptions(
            executable=executable,
            lua_bootstrap=config.lua_bootstrap.resolve(),
            run=True,
            stdout=True,
            lua_stdout=True,
            interpreter=True,
            debugger=True,
            testmode=True,
            portable_directory=run_dir / "portable",
        )
        adapter = PCSXReduxAdapter(options, transport)
        scratch_address = args.scratch_address
        if scratch_address is None:
            scratch_address = config.scratch_address
        runner = CapabilityRunner(
            adapter,
            transport,
            run_dir,
            executable=executable,
            version=version_info,
            architecture=local_architecture(),
            timeout_seconds=max(config.timeout_seconds, 10.0),
            allow_scratch_write=bool(args.allow_scratch_write),
            scratch_address=scratch_address,
            include_save_state_roundtrip=bool(args.include_save_state_roundtrip),
            include_breakpoint_smoke=bool(args.include_breakpoint_smoke),
        )
        report = runner.run()
    for check in report.checks:
        print(f"{check.status:4} {check.name:20} {check.detail}")
    print(f"JSON {run_dir / 'capabilities.json'}")
    return 0 if report.succeeded else 2


def command_init_config(args: argparse.Namespace) -> int:
    destination = Path(args.destination)
    if destination.exists() and not args.force:
        raise FileExistsError(f"refusing to overwrite {destination}; pass --force")
    source = Path(__file__).resolve().parents[2] / "config" / "project.example.toml"
    if not source.exists():
        source = Path("config/project.example.toml")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    print(destination)
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def command_inspect_input(args: argparse.Namespace) -> int:
    path = Path(args.path)
    stat = path.stat()
    with path.open("rb") as handle:
        header = handle.read(0x800)
    result: dict[str, Any] = {
        "filename": path.name,
        "size": stat.st_size,
        "sha256": _sha256(path),
        "format": "unknown",
    }
    if header.startswith(b"PS-X EXE") and len(header) >= 0x20:
        result.update(
            {
                "format": "PS-X EXE",
                "initial_pc": f"0x{struct.unpack_from('<I', header, 0x10)[0]:08X}",
                "load_address": f"0x{struct.unpack_from('<I', header, 0x18)[0]:08X}",
                "payload_size": struct.unpack_from("<I", header, 0x1C)[0],
            }
        )
    elif path.suffix.lower() == ".cue":
        result["format"] = "CUE sheet"
    elif path.suffix.lower() in {".bin", ".iso"}:
        result["format"] = "disc image (PS-X EXE not directly exposed)"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def command_inspect_disc(args: argparse.Namespace) -> int:
    metadata = inspect_disc_executable(Path(args.cue).resolve(), Path(args.extract_directory).resolve())
    print(json.dumps(metadata.to_dict(), indent=2, sort_keys=True))
    return 0


def command_r4_observe(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for read-only R4 observation")
    cue = Path(args.cue).resolve()
    if not cue.is_file():
        raise FileNotFoundError(cue)
    run_dir = config.runs_dir / "observations" / _timestamp_id("r4-boot")
    report = observe_r4_boot(
        executable,
        config.lua_bootstrap.resolve(),
        cue,
        run_dir,
        args.vblanks,
        max(float(args.timeout), config.timeout_seconds),
    )
    print(json.dumps({"run_dir": str(run_dir), "report": report}, indent=2, sort_keys=True))
    return 0


def command_capture_manual_state(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for manual state capture")
    cue = Path(args.cue).resolve() if args.cue else config.disc_path
    bios = Path(args.bios).resolve() if args.bios else config.bios_path
    output_directory = Path(args.output_directory).resolve() if args.output_directory else None
    result = run_manual_capture(
        config.root,
        config_path,
        executable,
        config.lua_bootstrap.resolve(),
        name=str(args.name),
        cue=cue,
        bios=bios,
        output_directory=output_directory,
        timeout_seconds=max(float(args.timeout), config.timeout_seconds),
        no_shutdown=bool(args.no_shutdown),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["validation_status"] == "FAIL" else 0


def command_replay_input(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for deterministic input replay")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for deterministic input replay")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    definitions = load_input_scenarios(Path(args.scenarios).resolve())
    names = list(args.scenario) if args.scenario else list(definitions)
    unknown = sorted(set(names) - set(definitions))
    if unknown:
        raise ValueError("unknown input scenarios: " + ", ".join(unknown))
    report_path, report = run_real_input_replays(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        [definitions[name] for name in names],
        attempts=int(args.attempts),
        sample_every=int(args.sample_every),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_trace_race(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for race tracing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for race tracing")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    report_path, report = trace_r4_race(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        telemetry_vblanks=int(args.vblanks),
        breakpoint_vblanks=int(args.breakpoint_vblanks),
        max_hits=int(args.max_hits),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_trace_functions(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for function tracing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for function tracing")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    addresses = tuple(int(value, 0) for value in args.address)
    report_path, report = trace_function_cadence(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        addresses,
        vblanks=int(args.vblanks),
        max_hits=int(args.max_hits),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_probe_overlay(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for overlay probing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for overlay probing")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    report_path, report = probe_runtime_overlay(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        int(args.address, 0),
        size=int(args.size),
        extract_length=int(args.extract_length, 0) if args.extract_length else None,
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_trace_addresses(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for targeted address tracing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for targeted address tracing")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    watches = tuple(parse_target_watch(value) for value in args.watch)
    report_path, report = trace_targeted_addresses(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        watches,
        vblanks=int(args.vblanks),
        max_write_hits=int(args.max_hits),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_render_cadence(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for render cadence measurement")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for render cadence measurement")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    report_path, report = measure_render_cadence(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        vblanks=int(args.vblanks),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_audit_scratch(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for scratch auditing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for scratch auditing")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    definitions = load_input_scenarios(Path(args.scenarios).resolve())
    report_path, report = audit_scratch_location(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        int(args.address, 0),
        tuple(definitions.values()),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_trace_loop_parity(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for loop parity tracing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for loop parity tracing")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    definitions = load_input_scenarios(Path(args.scenarios).resolve())
    if args.scenario not in definitions:
        raise ValueError(f"unknown input scenario: {args.scenario}")
    branches = load_branch_inventory(
        Path(args.branches).resolve(),
        assets.identity.sha256,
    )
    report_path, report = trace_loop_parity(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        definitions[args.scenario],
        branches,
        vblanks=int(args.vblanks),
        max_events=int(args.max_events),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_trace_gpu_buffers(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for GPU buffer tracing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for GPU buffer tracing")
    assets = discover_r4_assets(
        config.root,
        executable,
        cue_override=config.disc_path,
        bios_override=config.bios_path,
    )
    definitions = load_input_scenarios(Path(args.scenarios).resolve())
    if args.scenario not in definitions:
        raise ValueError(f"unknown input scenario: {args.scenario}")
    report_path, report = trace_gpu_buffers(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        definitions[args.scenario],
        vblanks=int(args.vblanks),
        max_nodes=int(args.max_nodes),
        max_bytes=int(args.max_bytes),
        max_events=int(args.max_events),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_trace_race_call_order(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for race call-order tracing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for race call-order tracing")
    assets = discover_r4_assets(
        config.root, executable, cue_override=config.disc_path, bios_override=config.bios_path
    )
    definitions = load_input_scenarios(Path(args.scenarios).resolve())
    if args.scenario not in definitions:
        raise ValueError(f"unknown input scenario: {args.scenario}")
    report_path, report = trace_race_call_order(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        definitions[args.scenario],
        frames=int(args.frames),
        max_events_per_frame=int(args.max_events_per_frame),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_trace_input_engine(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for input/engine tracing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for input/engine tracing")
    assets = discover_r4_assets(
        config.root, executable, cue_override=config.disc_path, bios_override=config.bios_path
    )
    definitions = load_input_scenarios(Path(args.scenarios).resolve())
    names = list(args.scenario) if args.scenario else list(definitions)
    unknown = sorted(set(names) - set(definitions))
    if unknown:
        raise ValueError("unknown input scenarios: " + ", ".join(unknown))
    report_path, report = trace_input_and_engine_state(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        [definitions[name] for name in names],
        vblanks=int(args.vblanks),
        sample_every=int(args.sample_every),
        max_hits=int(args.max_hits),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_trace_ai_trajectories(args: argparse.Namespace) -> int:
    config = _load_config(args)
    executable = discover_pcsx_redux(config.pcsx_executable)
    if executable is None:
        raise RuntimeError("PCSX-Redux is required for AI trajectory tracing")
    if config.save_state is None or not config.save_state.is_file():
        raise RuntimeError("a verified target.save_state is required for AI trajectory tracing")
    assets = discover_r4_assets(
        config.root, executable, cue_override=config.disc_path, bios_override=config.bios_path
    )
    definitions = load_input_scenarios(Path(args.scenarios).resolve())
    if args.scenario not in definitions:
        raise ValueError(f"unknown input scenario: {args.scenario}")
    report_path, report = trace_ai_trajectories(
        config.root,
        executable,
        config.lua_bootstrap.resolve(),
        config.save_state,
        assets,
        definitions[args.scenario],
        attempts=int(args.attempts),
        vblanks=int(args.vblanks),
        sample_every=int(args.sample_every),
        timeout_seconds=max(config.timeout_seconds, float(args.timeout)),
    )
    print(json.dumps({"status": report["status"], "report": str(report_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_baseline(args: argparse.Namespace) -> int:
    config = _load_config(args)
    run_id = args.id or _timestamp_id("baseline")
    proposal = ExperimentProposal(
        id=run_id,
        hypothesis="deterministic unmodified baseline",
        target_version=_target(config),
    )
    with ExperimentStore(config.database) as store:
        summary = _supervisor(config, store).run(
            proposal,
            kind="baseline",
            scenario=args.scenario,
            vblanks=args.vblanks or config.vblanks,
            save_state=config.save_state,
        )
    print(json.dumps({"run_id": run_id, "summary": summary.to_dict()}, indent=2, sort_keys=True))
    return 0


def command_experiment(args: argparse.Namespace) -> int:
    config = _load_config(args)
    with Path(args.proposal).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("proposal must be a JSON object")
    proposal = ExperimentProposal.from_dict(value)
    with ExperimentStore(config.database) as store:
        summary = _supervisor(config, store).run(
            proposal,
            kind="candidate",
            scenario=args.scenario or config.scenario,
            vblanks=args.vblanks or config.vblanks,
            save_state=config.save_state,
        )
    print(json.dumps({"run_id": proposal.id, "summary": summary.to_dict()}, indent=2, sort_keys=True))
    return 0


def command_compare(args: argparse.Namespace) -> int:
    config = _load_config(args)
    with ExperimentStore(config.database) as store:
        baseline_record = store.get(args.baseline_id)
        experiment_record = store.get(args.experiment_id)
        comparison = compare_summaries(
            args.baseline_id,
            args.experiment_id,
            summary_from_record(baseline_record),
            summary_from_record(experiment_record),
        )
        store.save_comparison(args.baseline_id, args.experiment_id, comparison.to_dict())
    baseline_trace = load_jsonl(Path(baseline_record["run_dir"]) / "telemetry.jsonl")
    experiment_trace = load_jsonl(Path(experiment_record["run_dir"]) / "telemetry.jsonl")
    evaluation = evaluate_trace_pair(baseline_trace, experiment_trace, Path(args.criteria))
    print(json.dumps({"comparison": comparison.to_dict(), "evaluation": evaluation}, indent=2, sort_keys=True))
    return 0


def command_visual_check(args: argparse.Namespace) -> int:
    stats = analyze_raw_screenshot(Path(args.raw), Path(args.metadata))
    print(json.dumps(stats.to_dict(), indent=2, sort_keys=True))
    return 0 if stats.valid_size else 2


def command_trace_summary(args: argparse.Namespace) -> int:
    config = _load_config(args)
    with ExperimentStore(config.database) as store:
        record = store.get(args.run_id)
    trace = Path(record["run_dir"]) / "telemetry.jsonl"
    summary = summarize_events(load_jsonl(trace))
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


def command_report(args: argparse.Namespace) -> int:
    config = _load_config(args)
    with ExperimentStore(config.database) as store:
        record = store.get(args.run_id)
        transitions = store.transitions(args.run_id)
    report = render_run_report(record, transitions)
    output = Path(args.output) if args.output else Path(record["run_dir"]) / "report.md"
    output.write_text(report, encoding="utf-8")
    print(output)
    return 0


def command_campaign(args: argparse.Namespace) -> int:
    path = Path(args.campaign_config)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    budget = dict(data.get("campaign", {}))
    required = {
        "max_experiments", "max_seconds", "max_codex_calls", "max_consecutive_crashes",
        "max_consecutive_no_progress", "max_storage_bytes", "max_vblanks_per_experiment",
        "max_changes_per_experiment", "max_retries_per_candidate", "max_cost",
    }
    missing = sorted(required - budget.keys())
    if missing:
        raise ValueError("campaign budget is missing: " + ", ".join(missing))
    mode = "execute" if args.execute else "dry-run"
    print(json.dumps({"mode": mode, "validated_budget": budget}, indent=2, sort_keys=True))
    if args.execute:
        if bool(args.fake_codex) == bool(args.real_codex):
            raise RuntimeError("campaign execution requires exactly one of --fake-codex or --real-codex")
        project = _load_config(args)
        stamp = _timestamp_id("campaign")
        campaign_budget = CampaignBudget.from_dict(budget)
        output_directory = project.runs_dir / "campaigns" / stamp
        if args.fake_codex:
            baseline = ExperimentProposal(stamp + "-baseline", "campaign fake baseline", _target(project))
            candidate_value = json.loads(
                (project.root / "config/fake_candidate.example.json").read_text(encoding="utf-8")
            )
            candidate_value["id"] = stamp + "-candidate"
            candidate = ExperimentProposal.from_dict(candidate_value)
            with ExperimentStore(project.database) as store:
                report = CampaignRunner(
                    store,
                    _supervisor(project, store),
                    FakeCodexClient([candidate]),
                    campaign_budget,
                    output_directory,
                ).run(baseline, args.scenario or project.scenario, args.vblanks or project.vblanks)
        else:
            if project.mode != "real":
                raise RuntimeError("real Codex campaign requires project.mode=real")
            codex = discover_codex()
            if codex is None:
                raise RuntimeError("a current Codex CLI executable was not found")
            codex_identity = verify_codex_executable(codex)
            with ExperimentStore(project.database) as store:
                report = ProposalCampaignRunner(
                    store,
                    CodexExecClient(
                        codex,
                        project.root / "schemas" / "experiment_proposal.schema.json",
                        output_directory / "codex",
                        enabled=True,
                        timeout_seconds=min(float(campaign_budget.max_seconds), 300.0),
                    ),
                    campaign_budget,
                    output_directory,
                    _target(project),
                    (
                        "target serial is SLPS-01800",
                        "target executable SHA-256 is 95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775",
                        "the captured race state is reproducible",
                        "raw displayed image changes at 29.97 Hz in exact two-VBlank runs",
                        "vehicle/AI dispatcher, camera, lap timer, and race overlay all execute at 30 Hz",
                        "the active race path is an integrated 30 Hz loop",
                        "no isolated render-only instruction or reviewed patch candidate exists",
                        "published candidate addresses were disproven for this build",
                    ),
                    allowed_change_fingerprints=frozenset(),
                ).run()
            report["codex_identity"] = codex_identity
            (output_directory / "campaign.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            with ExperimentStore(project.database) as store:
                store.save_campaign(
                    stamp,
                    "FAILED" if report.get("stop_reason") == "codex_client_error" else "COMPLETED",
                    report,
                )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2 if report.get("stop_reason") == "codex_client_error" else 0
    return 0


def command_stop(args: argparse.Namespace) -> int:
    config = _load_config(args)
    marker = config.root / ".r4-autolab.stop"
    marker.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    print(marker)
    return 0


def command_ghidra_export(args: argparse.Namespace) -> int:
    project = _load_config(args)
    input_file = Path(args.input).resolve()
    if not input_file.is_file():
        raise FileNotFoundError(input_file)
    addresses = tuple(int(value, 0) for value in args.address)
    script_directory = (Path(__file__).resolve().parents[2] / "ghidra_scripts").resolve()
    script_file = script_directory / "R4Export.java"
    prepare_script = script_directory / "R4Prepare.java"
    header = input_file.read_bytes()[:0x800]
    is_psx_exe = len(header) >= 0x20 and header.startswith(b"PS-X EXE")
    processor = args.processor
    loader: str | None = None
    loader_base: int | None = None
    loader_offset: int | None = None
    loader_length: int | None = None
    entry_point: int | None = None
    global_pointer: int | None = None
    block_name: str | None = None
    if is_psx_exe:
        entry_point = struct.unpack_from("<I", header, 0x10)[0]
        global_pointer = struct.unpack_from("<I", header, 0x14)[0]
        loader_base = struct.unpack_from("<I", header, 0x18)[0]
        loader_length = struct.unpack_from("<I", header, 0x1C)[0]
        loader_offset = 0x800
        if loader_length <= 0 or loader_offset + loader_length > input_file.stat().st_size:
            raise ValueError("PS-X EXE payload range is invalid")
        processor = processor or "MIPS:LE:32:default"
        loader = "BinaryLoader"
        block_name = "R4_PAYLOAD"
    elif args.binary_base is not None:
        loader = "BinaryLoader"
        loader_base = int(args.binary_base, 0)
        loader_offset = int(args.binary_file_offset, 0)
        loader_length = (
            int(args.binary_length, 0)
            if args.binary_length
            else input_file.stat().st_size - loader_offset
        )
        if loader_offset < 0 or loader_length <= 0 or loader_offset + loader_length > input_file.stat().st_size:
            raise ValueError("raw binary import range is invalid")
        entry_point = int(args.entry_point, 0) if args.entry_point else loader_base
        global_pointer = int(args.global_pointer, 0) if args.global_pointer else 0
        processor = processor or "MIPS:LE:32:default"
        block_name = str(args.block_name)
    import_options = {
        "loader": loader,
        "base": loader_base,
        "offset": loader_offset,
        "length": loader_length,
        "block": block_name,
        "entry": entry_point,
        "gp": global_pointer,
    }
    key = cache_key(input_file, script_file, addresses, processor, (prepare_script,), import_options)
    output = Path(args.output).resolve() if args.output else Path("runs/static-cache") / key / "export.json"
    output = output.resolve()
    if output.is_file() and not args.force:
        summary = load_static_export(output)
        print(json.dumps({"cached": True, "path": str(output), "summary": summary.__dict__}, indent=2, default=list))
        return 0
    executable = discover_analyze_headless(project.ghidra_headless)
    if not args.fake and executable is None:
        raise RuntimeError("Ghidra analyzeHeadless is not installed; rerun with --fake only for integration testing")
    config = GhidraRunConfig(
        analyze_headless=executable or Path("analyzeHeadless"),
        input_file=input_file,
        output_file=output,
        project_directory=output.parent / "project",
        script_directory=script_directory,
        addresses=addresses,
        processor=processor,
        timeout_seconds=float(args.timeout),
        loader=loader,
        loader_base_address=loader_base,
        loader_file_offset=loader_offset,
        loader_length=loader_length,
        loader_block_name=block_name,
        entry_point=entry_point,
        global_pointer=global_pointer,
    )
    runner = FakeGhidraRunner() if args.fake else GhidraHeadlessRunner()
    runner.run(config, output.parent / "ghidra.log")
    summary = load_static_export(output)
    print(json.dumps({"cached": False, "path": str(output), "summary": summary.__dict__}, indent=2, default=list))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="r4-autolab")
    parser.add_argument("--config", default="config/project.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor")
    doctor.set_defaults(func=command_doctor)

    init = subparsers.add_parser("init-config")
    init.add_argument("--destination", default="config/project.toml")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=command_init_config)

    inspect_input = subparsers.add_parser("inspect-input")
    inspect_input.add_argument("path")
    inspect_input.set_defaults(func=command_inspect_input)

    inspect_disc = subparsers.add_parser("inspect-disc")
    inspect_disc.add_argument("--cue", required=True)
    inspect_disc.add_argument("--extract-directory", default="private/extracted")
    inspect_disc.set_defaults(func=command_inspect_disc)

    observe = subparsers.add_parser("r4-observe")
    observe.add_argument("--cue", required=True)
    observe.add_argument("--vblanks", type=int, default=600)
    observe.add_argument("--timeout", type=float, default=30.0)
    observe.set_defaults(func=command_r4_observe)

    capture = subparsers.add_parser("capture-manual-state")
    capture.add_argument("--name", default="race-straight")
    capture.add_argument("--cue")
    capture.add_argument("--bios")
    capture.add_argument("--output-directory")
    capture.add_argument("--timeout", type=float, default=30.0)
    capture.add_argument("--no-shutdown", action="store_true")
    capture.set_defaults(func=command_capture_manual_state)

    replay_input = subparsers.add_parser("replay-input")
    replay_input.add_argument("--scenarios", default="config/input_scenarios.example.json")
    replay_input.add_argument("--scenario", action="append")
    replay_input.add_argument("--attempts", type=int, default=3)
    replay_input.add_argument("--sample-every", type=int, default=60)
    replay_input.add_argument("--timeout", type=float, default=60.0)
    replay_input.set_defaults(func=command_replay_input)

    trace_race = subparsers.add_parser("trace-race")
    trace_race.add_argument("--vblanks", type=int, default=600)
    trace_race.add_argument("--breakpoint-vblanks", type=int, default=120)
    trace_race.add_argument("--max-hits", type=int, default=32)
    trace_race.add_argument("--timeout", type=float, default=60.0)
    trace_race.set_defaults(func=command_trace_race)

    trace_functions = subparsers.add_parser("trace-functions")
    trace_functions.add_argument("--address", action="append", required=True)
    trace_functions.add_argument("--vblanks", type=int, default=120)
    trace_functions.add_argument("--max-hits", type=int, default=256)
    trace_functions.add_argument("--timeout", type=float, default=60.0)
    trace_functions.set_defaults(func=command_trace_functions)

    overlay = subparsers.add_parser("probe-overlay")
    overlay.add_argument("--address", required=True)
    overlay.add_argument("--size", type=int, default=64)
    overlay.add_argument("--extract-length")
    overlay.add_argument("--timeout", type=float, default=60.0)
    overlay.set_defaults(func=command_probe_overlay)

    targeted = subparsers.add_parser("trace-addresses")
    targeted.add_argument("--watch", action="append", required=True)
    targeted.add_argument("--vblanks", type=int, default=600)
    targeted.add_argument("--max-hits", type=int, default=32)
    targeted.add_argument("--timeout", type=float, default=60.0)
    targeted.set_defaults(func=command_trace_addresses)

    render_cadence = subparsers.add_parser("render-cadence")
    render_cadence.add_argument("--vblanks", type=int, default=120)
    render_cadence.add_argument("--timeout", type=float, default=60.0)
    render_cadence.set_defaults(func=command_render_cadence)

    scratch_audit = subparsers.add_parser("audit-scratch")
    scratch_audit.add_argument("--address", required=True)
    scratch_audit.add_argument("--scenarios", default="config/input_scenarios.example.json")
    scratch_audit.add_argument("--timeout", type=float, default=60.0)
    scratch_audit.set_defaults(func=command_audit_scratch)

    loop_parity = subparsers.add_parser("trace-loop-parity")
    loop_parity.add_argument("--scenarios", default="config/input_scenarios.example.json")
    loop_parity.add_argument("--scenario", default="accelerate-straight-600")
    loop_parity.add_argument("--branches", default="config/loop_parity_branches.example.json")
    loop_parity.add_argument("--vblanks", type=int, default=600)
    loop_parity.add_argument("--max-events", type=int, default=20000)
    loop_parity.add_argument("--timeout", type=float, default=60.0)
    loop_parity.set_defaults(func=command_trace_loop_parity)

    gpu_buffers = subparsers.add_parser("trace-gpu-buffers", aliases=["gpu-command-cadence"])
    gpu_buffers.add_argument("--scenarios", default="config/input_scenarios.example.json")
    gpu_buffers.add_argument("--scenario", default="accelerate-straight-600")
    gpu_buffers.add_argument("--vblanks", type=int, default=240)
    gpu_buffers.add_argument("--max-nodes", type=int, default=4096)
    gpu_buffers.add_argument("--max-bytes", type=int, default=1048576)
    gpu_buffers.add_argument("--max-events", type=int, default=10000)
    gpu_buffers.add_argument("--timeout", type=float, default=60.0)
    gpu_buffers.set_defaults(func=command_trace_gpu_buffers)

    call_order = subparsers.add_parser("trace-race-call-order")
    call_order.add_argument("--scenarios", default="config/input_scenarios.example.json")
    call_order.add_argument("--scenario", default="accelerate-straight-600")
    call_order.add_argument("--frames", type=int, default=30)
    call_order.add_argument("--max-events-per-frame", type=int, default=2048)
    call_order.add_argument("--timeout", type=float, default=60.0)
    call_order.set_defaults(func=command_trace_race_call_order)

    input_engine = subparsers.add_parser("trace-input-engine")
    input_engine.add_argument("--scenarios", default="config/input_scenarios.example.json")
    input_engine.add_argument("--scenario", action="append")
    input_engine.add_argument("--vblanks", type=int, default=120)
    input_engine.add_argument("--sample-every", type=int, default=2)
    input_engine.add_argument("--max-hits", type=int, default=64)
    input_engine.add_argument("--timeout", type=float, default=60.0)
    input_engine.set_defaults(func=command_trace_input_engine)

    ai_trajectories = subparsers.add_parser("trace-ai-trajectories")
    ai_trajectories.add_argument("--scenarios", default="config/input_scenarios.example.json")
    ai_trajectories.add_argument("--scenario", default="accelerate-straight-600")
    ai_trajectories.add_argument("--attempts", type=int, default=3)
    ai_trajectories.add_argument("--vblanks", type=int, default=600)
    ai_trajectories.add_argument("--sample-every", type=int, default=2)
    ai_trajectories.add_argument("--timeout", type=float, default=60.0)
    ai_trajectories.set_defaults(func=command_trace_ai_trajectories)

    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--scenario", required=True)
    baseline.add_argument("--id")
    baseline.add_argument("--vblanks", type=int)
    baseline.set_defaults(func=command_baseline)

    experiment = subparsers.add_parser("experiment")
    experiment.add_argument("--proposal", required=True)
    experiment.add_argument("--scenario")
    experiment.add_argument("--vblanks", type=int)
    experiment.set_defaults(func=command_experiment)

    compare = subparsers.add_parser("compare")
    compare.add_argument("baseline_id")
    compare.add_argument("experiment_id")
    compare.add_argument("--criteria", default="config/success_criteria.example.toml")
    compare.set_defaults(func=command_compare)

    trace = subparsers.add_parser("trace-summary")
    trace.add_argument("run_id")
    trace.set_defaults(func=command_trace_summary)

    report = subparsers.add_parser("report")
    report.add_argument("run_id")
    report.add_argument("--output")
    report.set_defaults(func=command_report)

    campaign = subparsers.add_parser("campaign")
    campaign.add_argument("--config", dest="campaign_config", required=True)
    campaign.add_argument("--execute", action="store_true")
    campaign.add_argument("--fake-codex", action="store_true")
    campaign.add_argument("--real-codex", action="store_true")
    campaign.add_argument("--scenario")
    campaign.add_argument("--vblanks", type=int)
    campaign.set_defaults(func=command_campaign)

    capabilities = subparsers.add_parser("pcsx-capabilities")
    capabilities.add_argument("--allow-scratch-write", action="store_true")
    capabilities.add_argument("--scratch-address", type=lambda value: int(value, 0))
    capabilities.add_argument("--include-save-state-roundtrip", action="store_true")
    capabilities.add_argument("--include-breakpoint-smoke", action="store_true")
    capabilities.set_defaults(func=command_pcsx_capabilities)

    ghidra_export = subparsers.add_parser("ghidra-export")
    ghidra_export.add_argument("--input", required=True)
    ghidra_export.add_argument("--address", action="append", default=[])
    ghidra_export.add_argument("--processor")
    ghidra_export.add_argument("--output")
    ghidra_export.add_argument("--timeout", type=float, default=600.0)
    ghidra_export.add_argument("--force", action="store_true")
    ghidra_export.add_argument("--fake", action="store_true")
    ghidra_export.add_argument("--binary-base")
    ghidra_export.add_argument("--binary-file-offset", default="0")
    ghidra_export.add_argument("--binary-length")
    ghidra_export.add_argument("--entry-point")
    ghidra_export.add_argument("--global-pointer")
    ghidra_export.add_argument("--block-name", default="R4_OVERLAY")
    ghidra_export.set_defaults(func=command_ghidra_export)

    visual = subparsers.add_parser("visual-check")
    visual.add_argument("--raw", required=True)
    visual.add_argument("--metadata", required=True)
    visual.set_defaults(func=command_visual_check)

    stop = subparsers.add_parser("stop")
    stop.set_defaults(func=command_stop)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
