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
    mode = str(project.get("mode", "fake"))
    if mode not in {"fake", "real"}:
        raise ValueError("project.mode must be 'fake' or 'real'")
    vblanks = int(experiment.get("vblanks", 120))
    if vblanks <= 0:
        raise ValueError("experiment.vblanks must be positive")
    save_value = str(target.get("save_state", ""))
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
    )

