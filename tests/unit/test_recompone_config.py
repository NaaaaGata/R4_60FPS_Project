from __future__ import annotations

import json
from pathlib import Path

import pytest

from r4_autolab.recompone.config import load_recompone_config


def _config(root: Path) -> Path:
    directory = root / "private/recompone/config"
    maps = root / "private/recompone/function-maps"
    directory.mkdir(parents=True)
    maps.mkdir(parents=True)
    (root / "game.cue").write_text('FILE "game.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")
    (maps / "main.json").write_text("{}\n", encoding="utf-8")
    (maps / "race.json").write_text("{}\n", encoding="utf-8")
    value = {
        "game": {"id": "SLPS-01800", "name": "R4Research", "output": "../generated/r4"},
        "cue": "../../../game.cue",
        "funcMap": "../function-maps/main.json",
        "main": "0x8007D4B4",
        "linearSweep": False,
        "debug": False,
        "overlays": [
            {
                "name": "race",
                "funcMap": "../function-maps/race.json",
                "base": "0x801146F0",
                "file": "R4.BIN",
                "offset": 0x261A000,
                "size": 0x46000,
                "linearSweep": False,
            }
        ],
        "stubs": [],
        "ignored": [],
        "patches": [],
    }
    path = directory / "r4.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_safe_config_resolves_only_bounded_project_paths(tmp_path: Path) -> None:
    path = _config(tmp_path)
    config = load_recompone_config(path, tmp_path)
    assert config.cue_path == (tmp_path / "game.cue").resolve()
    assert config.output_directory == (tmp_path / "private/recompone/generated/r4").resolve()
    assert len(config.host_inputs) == 2
    assert config.config.overlays[0].offset == 0x261A000


@pytest.mark.parametrize("field", ["linearSweep", "debug"])
def test_rejects_unsafe_global_modes(tmp_path: Path, field: str) -> None:
    path = _config(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value[field] = True
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match=field):
        load_recompone_config(path, tmp_path)


@pytest.mark.parametrize("field", ["stubs", "ignored", "patches"])
def test_rejects_stub_ignore_and_patch_shortcuts(tmp_path: Path, field: str) -> None:
    path = _config(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value[field] = [{"target": "unsafe"}] if field == "patches" else ["unsafe"]
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="must remain empty"):
        load_recompone_config(path, tmp_path)


def test_rejects_generated_output_outside_private_boundary(tmp_path: Path) -> None:
    path = _config(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["game"]["output"] = "../../../public-generated"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="private/recompone/generated"):
        load_recompone_config(path, tmp_path)


def test_rejects_unknown_config_fields(tmp_path: Path) -> None:
    path = _config(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["unsafe"] = True
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported fields"):
        load_recompone_config(path, tmp_path)


def test_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "private/recompone/config/broken.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_recompone_config(path, tmp_path)


def test_rejects_overlay_disc_escape_and_host_funcmap_escape(tmp_path: Path) -> None:
    disc_root = tmp_path / "disc"
    path = _config(disc_root)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["overlays"][0]["file"] = "../R4.BIN"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="relative path inside the disc"):
        load_recompone_config(path, disc_root)

    host_root = tmp_path / "host"
    path = _config(host_root)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["funcMap"] = "../../../../outside.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes the project root"):
        load_recompone_config(path, host_root)


def test_rejects_ambiguous_or_overflowing_overlay_source(tmp_path: Path) -> None:
    ambiguous_root = tmp_path / "ambiguous"
    path = _config(ambiguous_root)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["overlays"][0]["lba"] = 42
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        load_recompone_config(path, ambiguous_root)

    overflow_root = tmp_path / "overflow"
    path = _config(overflow_root)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["overlays"][0]["offset"] = 0x7FFFFFF0
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="overflows"):
        load_recompone_config(path, overflow_root)
