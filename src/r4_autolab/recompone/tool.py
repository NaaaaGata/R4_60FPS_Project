from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


PINNED_RECOMPONE_COMMIT = "3d8b0e1b6ab7ebf444e8d4d02e6320746ec62807"
_DOTNET_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


@dataclass(frozen=True)
class RecompOneTool:
    path: Path
    launcher: tuple[str, ...]
    source_root: Path | None
    commit: str | None
    source_dirty: bool | None
    dotnet_path: Path | None
    dotnet_version: str | None
    license_name: str | None

    @property
    def pinned(self) -> bool:
        return self.commit == PINNED_RECOMPONE_COMMIT

    def to_dict(self, *, relative_to: Path | None = None) -> dict[str, Any]:
        value = asdict(self)

        def display(item: Path | str | None) -> str | None:
            if item is None:
                return None
            path = Path(item)
            if relative_to is not None:
                try:
                    return f"<project>/{path.resolve().relative_to(relative_to.resolve())}"
                except ValueError:
                    pass
            return str(path)

        for key in ("path", "source_root", "dotnet_path"):
            value[key] = display(value[key])
        value["launcher"] = [display(item) for item in self.launcher]
        value["pinned"] = self.pinned
        return value


def _source_root(path: Path) -> Path | None:
    start = path if path.is_dir() else path.parent
    for candidate in (start, *start.parents):
        if (candidate / "RecompOne.sln").is_file() and (candidate / "LICENSE").is_file():
            return candidate
    return None


def _git_metadata(root: Path | None) -> tuple[str | None, bool | None]:
    if root is None or not (root / ".git").exists() or shutil.which("git") is None:
        return None, None
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def query_dotnet() -> tuple[Path | None, str | None]:
    found = shutil.which("dotnet")
    if found is None:
        return None, None
    path = Path(found).resolve()
    try:
        version = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return path, None
    return path, version if _DOTNET_VERSION.fullmatch(version) else None


def dotnet_is_supported(version: str | None) -> bool:
    if version is None:
        return False
    match = _DOTNET_VERSION.fullmatch(version)
    return match is not None and int(match.group(1)) >= 10


def _candidate_tool(candidate: Path) -> RecompOneTool | None:
    resolved = candidate.expanduser().resolve()
    source = _source_root(resolved)
    dotnet_path, dotnet_version = query_dotnet()
    executable: Path | None = None
    launcher: tuple[str, ...]
    if resolved.is_dir():
        paths = (
            resolved / "RecompOne.Recompiler/bin/Release/net10.0/recompone.dll",
            resolved / "RecompOne.Recompiler/bin/Debug/net10.0/recompone.dll",
        )
        executable = next((item.resolve() for item in paths if item.is_file()), None)
        if executable is None:
            return None
    elif resolved.is_file():
        executable = resolved
    else:
        return None
    if executable.suffix.lower() == ".dll":
        if dotnet_path is None or not dotnet_is_supported(dotnet_version):
            return None
        launcher = (str(dotnet_path), str(executable))
    elif os.access(executable, os.X_OK):
        launcher = (str(executable),)
    else:
        return None
    source = source or _source_root(executable)
    commit, dirty = _git_metadata(source)
    license_name = "MIT" if source is not None and "MIT License" in (source / "LICENSE").read_text(
        encoding="utf-8", errors="replace"
    ) else None
    return RecompOneTool(
        path=executable,
        launcher=launcher,
        source_root=source,
        commit=commit,
        source_dirty=dirty,
        dotnet_path=dotnet_path,
        dotnet_version=dotnet_version,
        license_name=license_name,
    )


def discover_recompone(configured: Path | None = None) -> RecompOneTool | None:
    candidates: list[Path] = []
    environment = os.environ.get("R4_AUTOLAB_RECOMPONE")
    if environment:
        candidates.append(Path(environment))
    if configured is not None:
        candidates.append(configured)
    found = shutil.which("recompone")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        tool = _candidate_tool(candidate)
        if tool is not None:
            return tool
    return None
