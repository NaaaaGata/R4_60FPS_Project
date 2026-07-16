from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


@dataclass(frozen=True)
class GhidraRunConfig:
    analyze_headless: Path
    input_file: Path
    output_file: Path
    project_directory: Path
    script_directory: Path
    addresses: tuple[int, ...] = ()
    processor: str | None = None
    timeout_seconds: float = 600.0
    loader: str | None = None
    loader_base_address: int | None = None
    loader_file_offset: int | None = None
    loader_length: int | None = None
    loader_block_name: str | None = None
    entry_point: int | None = None
    global_pointer: int | None = None


def discover_analyze_headless(configured: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    environment = os.environ.get("R4_AUTOLAB_GHIDRA_HEADLESS")
    if environment:
        candidates.append(Path(environment).expanduser())
    if configured is not None:
        candidates.append(configured.expanduser())
    found = shutil.which("analyzeHeadless")
    if found:
        candidates.append(Path(found))
    candidates.extend(Path("/Applications").glob("ghidra*/support/analyzeHeadless"))
    candidates.extend((Path.home() / "Applications").glob("ghidra*/support/analyzeHeadless"))
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def build_headless_args(config: GhidraRunConfig) -> list[str]:
    arguments = [
        str(config.analyze_headless),
        str(config.project_directory),
        "r4-autolab-temp",
        "-import",
        str(config.input_file),
        "-overwrite",
        "-analysisTimeoutPerFile",
        str(max(1, int(config.timeout_seconds))),
    ]
    if config.processor:
        arguments.extend(["-processor", config.processor])
    if config.loader:
        arguments.extend(["-loader", config.loader])
    if config.loader_base_address is not None:
        arguments.extend(["-loader-baseAddr", f"0x{config.loader_base_address:08X}"])
    if config.loader_file_offset is not None:
        arguments.extend(["-loader-fileOffset", f"0x{config.loader_file_offset:X}"])
    if config.loader_length is not None:
        # BinaryLoader's option parser expects an address-style hexadecimal value.
        arguments.extend(["-loader-length", f"0x{config.loader_length:X}"])
    if config.loader_block_name:
        arguments.extend(["-loader-blockName", config.loader_block_name])
    arguments.extend(
        [
            "-scriptPath",
            str(config.script_directory),
        ]
    )
    if config.entry_point is not None:
        arguments.extend(
            [
                "-preScript",
                "R4Prepare.java",
                f"0x{config.entry_point:08X}",
                f"0x{(config.global_pointer or 0):08X}",
                f"0x{(config.loader_base_address or 0):08X}",
                str(config.loader_length or 0),
            ]
        )
    arguments.extend(
        [
            "-postScript",
            "R4Export.java",
            str(config.output_file),
            *[f"0x{address:08X}" for address in config.addresses],
            "-deleteProject",
        ]
    )
    return arguments


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def cache_key(
    input_file: Path,
    script_file: Path,
    addresses: tuple[int, ...],
    processor: str | None,
    additional_script_files: tuple[Path, ...] = (),
) -> str:
    digest = hashlib.sha256()
    digest.update(_sha256(input_file).encode("ascii"))
    digest.update(_sha256(script_file).encode("ascii"))
    for additional in additional_script_files:
        digest.update(_sha256(additional).encode("ascii"))
    digest.update(json.dumps({"addresses": addresses, "processor": processor}, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


class GhidraHeadlessRunner:
    def run(self, config: GhidraRunConfig, log_path: Path) -> Path:
        config.project_directory.mkdir(parents=True, exist_ok=True)
        config.output_file.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as log:
            subprocess.run(
                build_headless_args(config),
                stdout=log,
                stderr=subprocess.STDOUT,
                shell=False,
                timeout=config.timeout_seconds + 30,
                check=True,
            )
        if not config.output_file.is_file():
            raise RuntimeError("Ghidra completed without creating the requested JSON export")
        return config.output_file


class FakeGhidraRunner:
    def run(self, config: GhidraRunConfig, log_path: Path) -> Path:
        config.output_file.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        value: dict[str, Any] = {
            "input_sha256": _sha256(config.input_file),
            "language_id": config.processor or "MIPS:LE:32:default",
            "image_base": "0x80010000",
            "requested_addresses": [f"0x{address:08X}" for address in config.addresses],
            "functions": [],
            "basic_blocks": [],
            "calls": [],
            "xrefs": [],
            "strings": [],
            "overlays": [],
            "disassembly": [],
            "fake": True,
        }
        config.output_file.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        log_path.write_text("fake Ghidra export\n", encoding="utf-8")
        return config.output_file
