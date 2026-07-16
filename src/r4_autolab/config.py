from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    mode: str
    runs_dir: Path
    database: Path
    serial: str
    executable_sha256: str
    scenario: str
    vblanks: int
    timeout_seconds: float
    save_state: Path | None
    pcsx_executable: Path | None
    lua_bootstrap: Path
    bios_path: Path | None
    disc_path: Path | None
    scratch_address: int | None
    ghidra_headless: Path | None


def _resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def load_project_config(path: Path) -> ProjectConfig:
    with path.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    root = path.resolve().parent.parent
    project = data.get("project", {})
    target = data.get("target", {})
    experiment = data.get("experiment", {})
    emulator = data.get("emulator", {})
    tools = data.get("tools", {})
    mode = str(project.get("mode", "fake"))
    if mode not in {"fake", "real"}:
        raise ValueError("project.mode must be 'fake' or 'real'")
    vblanks = int(experiment.get("vblanks", 120))
    if vblanks <= 0:
        raise ValueError("experiment.vblanks must be positive")
    save_value = str(target.get("save_state", ""))
    executable_value = str(emulator.get("executable", ""))
    bootstrap_value = str(emulator.get("lua_bootstrap", "lua/bootstrap.lua"))
    bios_value = str(target.get("bios_path", ""))
    disc_value = str(target.get("disc_path", ""))
    raw_scratch = emulator.get("scratch_address")
    ghidra_value = str(tools.get("ghidra_headless", ""))
    scratch_address = (
        int(raw_scratch, 0) if isinstance(raw_scratch, str) else int(raw_scratch)
    ) if raw_scratch is not None and raw_scratch != "" else None
    return ProjectConfig(
        root=root,
        mode=mode,
        runs_dir=_resolve(root, str(project.get("runs_dir", "runs"))),
        database=_resolve(root, str(project.get("database", "runs/experiments.sqlite3"))),
        serial=str(target.get("serial", "unknown-until-verified")),
        executable_sha256=str(target.get("executable_sha256", "")),
        scenario=str(experiment.get("scenario", "fake-straight")),
        vblanks=vblanks,
        timeout_seconds=float(emulator.get("request_timeout_seconds", 5.0)),
        save_state=_resolve(root, save_value) if save_value else None,
        pcsx_executable=_resolve(root, executable_value) if executable_value else None,
        lua_bootstrap=_resolve(root, bootstrap_value),
        bios_path=_resolve(root, bios_value) if bios_value else None,
        disc_path=_resolve(root, disc_value) if disc_value else None,
        scratch_address=scratch_address,
        ghidra_headless=_resolve(root, ghidra_value) if ghidra_value else None,
    )
