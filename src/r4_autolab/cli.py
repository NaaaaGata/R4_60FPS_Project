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
from .evaluator import compare_summaries, load_jsonl, summary_from_record, summarize_events
from .models import ExperimentProposal, TargetVersion
from .reporting.markdown import render_run_report
from .storage import ExperimentStore
from .supervisor import ExperimentSupervisor


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


def command_doctor(_: argparse.Namespace) -> int:
    python_ok = sys.version_info >= (3, 11)
    pcsx_path = discover_pcsx_redux()
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
        ("Ghidra analyzeHeadless", os.environ.get("R4_AUTOLAB_GHIDRA_HEADLESS") or shutil.which("analyzeHeadless"), None, False, True),
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
    print(json.dumps(comparison.to_dict(), indent=2, sort_keys=True))
    return 0


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
        raise RuntimeError("campaign execution is intentionally deferred until resumable policy tests are added")
    return 0


def command_stop(args: argparse.Namespace) -> int:
    config = _load_config(args)
    marker = config.root / ".r4-autolab.stop"
    marker.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    print(marker)
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
    campaign.set_defaults(func=command_campaign)

    capabilities = subparsers.add_parser("pcsx-capabilities")
    capabilities.add_argument("--allow-scratch-write", action="store_true")
    capabilities.add_argument("--scratch-address", type=lambda value: int(value, 0))
    capabilities.add_argument("--include-save-state-roundtrip", action="store_true")
    capabilities.add_argument("--include-breakpoint-smoke", action="store_true")
    capabilities.set_defaults(func=command_pcsx_capabilities)

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
