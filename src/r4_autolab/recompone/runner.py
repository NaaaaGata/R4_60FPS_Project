from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import threading
import time
from typing import Any, Sequence

from ..analysis.iso9660 import cue_bin_path
from .config import ValidatedRecompOneConfig
from .tool import RecompOneTool


@dataclass(frozen=True)
class BoundedProcessResult:
    command: tuple[str, ...]
    exit_code: int
    duration_seconds: float
    timed_out: bool
    log_limit_exceeded: bool
    log_bytes: int
    forced_cleanup: bool
    residual_processes: bool

    @property
    def succeeded(self) -> bool:
        return (
            self.exit_code == 0
            and not self.timed_out
            and not self.log_limit_exceeded
            and not self.residual_processes
        )


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        if process.poll() is None:
            process.kill()


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_group_exit(process_group: int, timeout_seconds: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while _process_group_exists(process_group):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


def run_bounded_process(
    command: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout_seconds: float,
    max_log_bytes: int,
) -> BoundedProcessResult:
    if timeout_seconds <= 0 or max_log_bytes <= 0:
        raise ValueError("timeout and maximum log size must be positive")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        start_new_session=True,
    )
    stdout = process.stdout
    if stdout is None:
        raise RuntimeError("failed to capture RecompOne output")
    captured = bytearray()
    exceeded = threading.Event()

    def read_output() -> None:
        while True:
            chunk = stdout.read(65536)
            if not chunk:
                break
            remaining = max_log_bytes - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            if len(chunk) > remaining:
                exceeded.set()
                _kill_process_group(process)
                break

    reader = threading.Thread(target=read_output, name="recompone-log-reader", daemon=True)
    started = time.monotonic()
    reader.start()
    timed_out = False
    forced_cleanup = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        forced_cleanup = True
        _kill_process_group(process)
        process.wait(timeout=5)
    if _process_group_exists(process.pid):
        forced_cleanup = True
        _kill_process_group(process)
    reader.join(timeout=5)
    if reader.is_alive():
        forced_cleanup = True
        _kill_process_group(process)
        stdout.close()
        reader.join(timeout=1)
    residual_processes = not _wait_for_process_group_exit(process.pid)
    duration = time.monotonic() - started
    log_path.write_bytes(bytes(captured))
    return BoundedProcessResult(
        command=tuple(command),
        exit_code=int(process.returncode if process.returncode is not None else -1),
        duration_seconds=duration,
        timed_out=timed_out,
        log_limit_exceeded=exceeded.is_set(),
        log_bytes=len(captured),
        forced_cleanup=forced_cleanup or exceeded.is_set(),
        residual_processes=residual_processes,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _log_analysis(log_path: Path) -> dict[str, Any]:
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    lowered = text.lower()
    unknown = [line for line in text.splitlines() if line.startswith("[Unknown]")]
    unmapped = [line for line in text.splitlines() if "unmapped call" in line.lower()]
    collisions = [line for line in text.splitlines() if "collision" in line.lower()]
    function_sources = {
        match.group(1): int(match.group(2))
        for match in re.finditer(r"emiting\s+(\S+)\.cs\s+\((\d+) functions\)", text)
    }
    jump_tables = {
        match.group(1): {"functions": int(match.group(2)), "entries": int(match.group(3))}
        for match in re.finditer(
            r"(\S+): found jump tables in (\d+) function\(s\), (\d+) entries in total",
            text,
        )
    }
    total_match = re.search(r"total functions:\s*(\d+)", text)
    reimplementations_match = re.search(r"applied\s+(\d+) reimplementations", text)
    return {
        "unknown_instructions": len(unknown),
        "unknown_instruction_details": unknown,
        "unmapped_calls": lowered.count("unmapped call"),
        "unmapped_call_details": unmapped,
        "overlay_collisions": lowered.count("collision"),
        "overlay_collision_details": collisions,
        "generated_functions": int(total_match.group(1)) if total_match else None,
        "generated_functions_by_source": function_sources,
        "jump_tables": jump_tables,
        "reimplementations": int(reimplementations_match.group(1)) if reimplementations_match else None,
    }


def _funcmap_inventory(config: ValidatedRecompOneConfig) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for index, path in enumerate(config.host_inputs):
        value = json.loads(path.read_text(encoding="utf-8"))
        functions = value.get("functions") if isinstance(value, dict) else None
        inventory.append(
            {
                "role": "main" if index == 0 else config.config.overlays[index - 1].name,
                "sha256": _sha256(path),
                "function_count": len(functions) if isinstance(functions, list) else None,
            }
        )
    return inventory


def _display_path(path: Path, root: Path) -> str:
    try:
        return f"<project>/{path.resolve().relative_to(root.resolve())}"
    except ValueError:
        return f"<external>/{path.name}"


def _process_report(
    process: BoundedProcessResult,
    root: Path,
    replacements: dict[str, str] | None = None,
) -> dict[str, Any]:
    value = asdict(process)
    replacements = replacements or {}
    command: list[str] = []
    for item in process.command:
        replacement = replacements.get(item)
        if replacement is not None:
            command.append(replacement)
            continue
        candidate = Path(item)
        command.append(_display_path(candidate, root) if candidate.is_absolute() else item)
    value["command"] = command
    return value


def git_ignores_path(project_root: Path, path: Path) -> bool | None:
    if not (project_root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "check-ignore", "--quiet", "--", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0


def _generated_inventory(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    return [
        {
            "name": str(path.relative_to(directory)),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(directory.glob("*.cs"))
        if path.is_file()
    ]


def _unmapped_dispatch_candidates(directory: Path) -> list[str]:
    calls: set[int] = set()
    mapped: set[int] = set()
    for path in (sorted(directory.glob("*.cs")) if directory.is_dir() else []):
        text = path.read_text(encoding="utf-8", errors="replace")
        calls.update(
            int(match, 16)
            for match in re.findall(r"Dispatcher\.Call\(c, m, 0x([0-9A-Fa-f]{1,8})u\)", text)
        )
        mapped.update(
            int(match, 16)
            for match in re.findall(r"\[0x([0-9A-Fa-f]{1,8})u\]\s*=", text)
        )
    return [f"0x{address:08X}" for address in sorted(calls - mapped)]


class RecompOneRunner:
    def __init__(
        self,
        tool: RecompOneTool,
        *,
        timeout_seconds: float = 300.0,
        max_log_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self.tool = tool
        self.timeout_seconds = timeout_seconds
        self.max_log_bytes = max_log_bytes

    def build_args(self, config: ValidatedRecompOneConfig) -> list[str]:
        return [*self.tool.launcher, str(config.path)]

    def generate(self, config: ValidatedRecompOneConfig, run_directory: Path) -> dict[str, Any]:
        run_directory.mkdir(parents=True, exist_ok=False)
        started_at = datetime.now(UTC).isoformat()
        cue = config.cue_path
        disc_bin = cue_bin_path(cue).resolve()
        before = {"cue": _sha256(cue), "bin": _sha256(disc_bin)}
        log_path = run_directory / "recompone.log"
        process = run_bounded_process(
            self.build_args(config),
            cwd=config.path.parent,
            log_path=log_path,
            timeout_seconds=self.timeout_seconds,
            max_log_bytes=self.max_log_bytes,
        )
        after = {"cue": _sha256(cue), "bin": _sha256(disc_bin)}
        analysis = _log_analysis(log_path)
        inventory = _generated_inventory(config.output_directory)
        unmapped_candidates = _unmapped_dispatch_candidates(config.output_directory)
        analysis["unmapped_call_log_events"] = analysis["unmapped_calls"]
        analysis["unmapped_call_candidates"] = len(unmapped_candidates)
        analysis["unmapped_call_candidate_addresses"] = unmapped_candidates
        analysis["unmapped_calls"] = int(analysis["unmapped_calls"]) + len(unmapped_candidates)
        hashes_unchanged = before == after
        generated_git_ignored = git_ignores_path(config.project_root, config.output_directory)
        status = "PASS" if (
            process.succeeded
            and hashes_unchanged
            and bool(inventory)
            and analysis["unknown_instructions"] == 0
            and analysis["unmapped_calls"] == 0
            and analysis["overlay_collisions"] == 0
            and generated_git_ignored is not False
        ) else "FAIL"
        safe_process = _process_report(
            process,
            config.project_root,
            {str(config.path): "<private-config>"},
        )
        report: dict[str, Any] = {
            "protocol_version": 1,
            "started_at": started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "status": status,
            "evidence": "RECOMP_STATIC_ONLY",
            "tool": self.tool.to_dict(relative_to=config.project_root),
            "host": {
                "os": platform.system(),
                "release": platform.release(),
                "architecture": platform.machine(),
            },
            "target": {"serial": config.config.game.id, "main": config.config.main},
            "config_sha256": config.sha256,
            "command": safe_process["command"],
            "process": safe_process,
            "asset_hashes_before": before,
            "asset_hashes_after": after,
            "source_hashes_unchanged": hashes_unchanged,
            "func_maps": _funcmap_inventory(config),
            "overlays": [
                {
                    "name": overlay.name,
                    "base": overlay.base,
                    "source": overlay.file if overlay.file is not None else f"LBA:{overlay.lba}",
                    "offset": overlay.offset,
                    "size": overlay.size,
                }
                for overlay in config.config.overlays
            ],
            "generated_files": inventory,
            "generated_git_ignored": generated_git_ignored,
            **analysis,
            "stubs": len(config.config.stubs),
            "ignored": len(config.config.ignored),
            "patches": len(config.config.patches),
            "runtime_started": False,
            "r4_memory_writes": 0,
            "pcsx_baseline": "docs/FINAL_AUDIT.md (integrated 30Hz, RESULT_C)",
        }
        (run_directory / "generation.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return report


def compile_generated_project(
    tool: RecompOneTool,
    generated_directory: Path,
    run_directory: Path,
    *,
    project_root: Path,
    timeout_seconds: float = 300.0,
    max_log_bytes: int = 4 * 1024 * 1024,
) -> dict[str, Any]:
    if tool.source_root is None:
        raise RuntimeError("generated compilation requires a RecompOne source checkout")
    runtime_project = tool.source_root / "RecompOne.Runtime/RecompOne.Runtime.csproj"
    if not runtime_project.is_file():
        raise FileNotFoundError(runtime_project)
    generated = generated_directory.resolve()
    if not generated.is_dir() or not list(generated.glob("*.cs")):
        raise RuntimeError("generated C# sources were not found")
    project = generated / "R4Generated.csproj"
    project.write_text(
        "\n".join(
            [
                '<Project Sdk="Microsoft.NET.Sdk">',
                "  <PropertyGroup>",
                "    <TargetFramework>net10.0</TargetFramework>",
                "    <ImplicitUsings>enable</ImplicitUsings>",
                "    <Nullable>enable</Nullable>",
                "    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>",
                "  </PropertyGroup>",
                "  <ItemGroup>",
                f'    <ProjectReference Include="{runtime_project}" />',
                "  </ItemGroup>",
                "</Project>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_directory.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    log_path = run_directory / "compile.log"
    dotnet = tool.dotnet_path
    if dotnet is None:
        raise RuntimeError("dotnet was not detected")
    process = run_bounded_process(
        [
            str(dotnet),
            "build",
            str(project),
            "--configuration",
            "Release",
            "--no-incremental",
            "--disable-build-servers",
            "-p:UseSharedCompilation=false",
            "-nodeReuse:false",
        ],
        cwd=generated,
        log_path=log_path,
        timeout_seconds=timeout_seconds,
        max_log_bytes=max_log_bytes,
    )
    root = project_root.resolve()
    compile_text = log_path.read_text(encoding="utf-8", errors="replace")
    warning_matches = re.findall(r"(\d+) Warning\(s\)", compile_text)
    error_matches = re.findall(r"(\d+) Error\(s\)", compile_text)
    report: dict[str, Any] = {
        "protocol_version": 1,
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if process.succeeded else "FAIL",
        "evidence": "RECOMP_STATIC_ONLY",
        "tool": tool.to_dict(relative_to=root),
        "process": _process_report(
            process,
            root,
            {str(project): "<generated-project>"},
        ),
        "project_sha256": _sha256(project),
        "warnings": int(warning_matches[-1]) if warning_matches else None,
        "errors": int(error_matches[-1]) if error_matches else None,
        "runtime_started": False,
        "r4_memory_writes": 0,
    }
    (run_directory / "compile.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
