from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


_HEX_ADDRESS = re.compile(r"^(?:0x)?[0-9A-Fa-f]{1,8}$")


@dataclass(frozen=True)
class RecompOneGameConfig:
    id: str
    name: str
    output: str


@dataclass(frozen=True)
class RecompOneOverlayConfig:
    name: str
    func_map: str | None
    base: str | None
    file: str | None
    offset: int
    skip: int
    lba: int
    size: int | None
    linear_sweep: bool | None


@dataclass(frozen=True)
class RecompOneConfig:
    game: RecompOneGameConfig
    cue: str
    func_map: str | None
    main: str | None
    linear_sweep: bool
    debug: bool
    overlays: tuple[RecompOneOverlayConfig, ...]
    stubs: tuple[str, ...]
    ignored: tuple[str, ...]
    patches: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ValidatedRecompOneConfig:
    path: Path
    project_root: Path
    config: RecompOneConfig
    cue_path: Path
    output_directory: Path
    host_inputs: tuple[Path, ...]
    sha256: str


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _optional_string(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    return _string(value, field)


def _integer(value: Any, field: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _string_array(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return tuple(_string(item, field) for item in value)


def _reject_unknown(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{field} has unsupported fields: " + ", ".join(unknown))


def _parse_overlay(value: Any, index: int) -> RecompOneOverlayConfig:
    field = f"overlays[{index}]"
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    _reject_unknown(
        value,
        {"name", "funcMap", "base", "file", "offset", "skip", "lba", "size", "linearSweep"},
        field,
    )
    linear = value.get("linearSweep")
    if linear is not None and not isinstance(linear, bool):
        raise ValueError(f"{field}.linearSweep must be a boolean")
    size_value = value.get("size")
    size = None if size_value is None else _integer(size_value, f"{field}.size", 0)
    return RecompOneOverlayConfig(
        name=_string(value.get("name"), f"{field}.name"),
        func_map=_optional_string(value.get("funcMap"), f"{field}.funcMap"),
        base=_optional_string(value.get("base"), f"{field}.base"),
        file=_optional_string(value.get("file"), f"{field}.file"),
        offset=_integer(value.get("offset"), f"{field}.offset", 0),
        skip=_integer(value.get("skip"), f"{field}.skip", 0),
        lba=_integer(value.get("lba"), f"{field}.lba", -1),
        size=size,
        linear_sweep=linear,
    )


def _parse_config(value: Any) -> RecompOneConfig:
    if not isinstance(value, dict):
        raise ValueError("RecompOne config must be a JSON object")
    _reject_unknown(
        value,
        {"game", "cue", "funcMap", "main", "linearSweep", "debug", "overlays", "stubs", "ignored", "patches"},
        "config",
    )
    game_value = value.get("game")
    if not isinstance(game_value, dict):
        raise ValueError("game must be an object")
    _reject_unknown(game_value, {"id", "name", "output"}, "game")
    overlays_value = value.get("overlays", [])
    if not isinstance(overlays_value, list):
        raise ValueError("overlays must be an array")
    patches_value = value.get("patches", [])
    if not isinstance(patches_value, list) or any(not isinstance(item, dict) for item in patches_value):
        raise ValueError("patches must be an array of objects")
    linear_sweep = value.get("linearSweep", False)
    debug = value.get("debug", False)
    if not isinstance(linear_sweep, bool) or not isinstance(debug, bool):
        raise ValueError("linearSweep and debug must be booleans")
    main = _optional_string(value.get("main"), "main")
    if main is not None and _HEX_ADDRESS.fullmatch(main) is None:
        raise ValueError("main must be a 32-bit hexadecimal address")
    return RecompOneConfig(
        game=RecompOneGameConfig(
            id=_string(game_value.get("id"), "game.id"),
            name=_string(game_value.get("name"), "game.name"),
            output=_string(game_value.get("output"), "game.output"),
        ),
        cue=_string(value.get("cue"), "cue"),
        func_map=_optional_string(value.get("funcMap"), "funcMap"),
        main=main,
        linear_sweep=linear_sweep,
        debug=debug,
        overlays=tuple(_parse_overlay(item, index) for index, item in enumerate(overlays_value)),
        stubs=_string_array(value.get("stubs"), "stubs"),
        ignored=_string_array(value.get("ignored"), "ignored"),
        patches=tuple(dict(item) for item in patches_value),
    )


def _contained(path: Path, root: Path, field: str) -> Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"{field} escapes the project root")
    return resolved


def _host_path(config_path: Path, raw: str, project_root: Path, field: str) -> Path:
    path = Path(raw).expanduser()
    candidate = path if path.is_absolute() else config_path.parent / path
    return _contained(candidate, project_root, field)


def _validate_disc_path(value: str, field: str) -> None:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError(f"{field} must be a relative path inside the disc image")


def load_recompone_config(
    path: Path,
    project_root: Path,
    *,
    require_files: bool = True,
) -> ValidatedRecompOneConfig:
    resolved_path = path.resolve()
    root = project_root.resolve()
    _contained(resolved_path, root, "config path")
    value = json.loads(resolved_path.read_text(encoding="utf-8"))
    config = _parse_config(value)
    if config.linear_sweep:
        raise ValueError("linearSweep is forbidden during the initial RecompOne phases")
    if config.debug:
        raise ValueError("debug is forbidden because unbounded per-function output is unsafe")
    if config.stubs or config.ignored or config.patches:
        raise ValueError("stubs, ignored functions, and patches must remain empty")
    if config.func_map is None:
        raise ValueError("funcMap is required while linear sweep is disabled")
    cue_path = _host_path(resolved_path, config.cue, root, "cue")
    output = _host_path(resolved_path, config.game.output, root, "game.output")
    generated_root = (root / "private/recompone/generated").resolve()
    if output != generated_root and generated_root not in output.parents:
        raise ValueError("game.output must stay inside private/recompone/generated")
    inputs: list[Path] = []
    if config.func_map is not None:
        inputs.append(_host_path(resolved_path, config.func_map, root, "funcMap"))
    names: set[str] = set()
    for index, overlay in enumerate(config.overlays):
        field = f"overlays[{index}]"
        if overlay.name in names:
            raise ValueError(f"duplicate overlay name: {overlay.name}")
        names.add(overlay.name)
        if overlay.linear_sweep:
            raise ValueError(f"{field}.linearSweep must not be enabled")
        if overlay.offset < 0 or overlay.skip < 0 or overlay.lba < -1:
            raise ValueError(f"{field} offsets and LBA are out of range")
        extent = overlay.offset + overlay.skip + (overlay.size or 0)
        if extent > 0x7FFFFFFF:
            raise ValueError(f"{field} offset overflows RecompOne's signed integer range")
        if overlay.size is not None and overlay.size <= 0:
            raise ValueError(f"{field}.size must be positive")
        if overlay.lba >= 0 and overlay.size is None:
            raise ValueError(f"{field}.size is required with lba")
        if overlay.file is None and overlay.lba < 0:
            raise ValueError(f"{field} requires file or lba")
        if overlay.file is not None and overlay.lba >= 0:
            raise ValueError(f"{field} must select exactly one of file or lba")
        if overlay.file is not None:
            _validate_disc_path(overlay.file, f"{field}.file")
        if overlay.base is None or _HEX_ADDRESS.fullmatch(overlay.base) is None:
            raise ValueError(f"{field}.base must be a 32-bit hexadecimal address")
        if int(overlay.base, 16) & 3:
            raise ValueError(f"{field}.base must be 4-byte aligned")
        if overlay.size is not None and int(overlay.base, 16) + overlay.size > 0x100000000:
            raise ValueError(f"{field} mapped range overflows the 32-bit address space")
        if overlay.func_map is None:
            raise ValueError(f"{field}.funcMap is required while linear sweep is disabled")
        inputs.append(_host_path(resolved_path, overlay.func_map, root, f"{field}.funcMap"))
    if require_files:
        for candidate in (cue_path, *inputs):
            if not candidate.is_file():
                raise FileNotFoundError(candidate)
    digest = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    return ValidatedRecompOneConfig(
        path=resolved_path,
        project_root=root,
        config=config,
        cue_path=cue_path,
        output_directory=output,
        host_inputs=tuple(inputs),
        sha256=digest,
    )
