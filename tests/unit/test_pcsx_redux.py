from pathlib import Path

import pytest

from r4_autolab.emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter, build_pcsx_redux_args


def test_argument_builder_uses_verified_flags_and_optional_paths(tmp_path: Path) -> None:
    options = PCSXLaunchOptions(
        executable=Path("/Applications/PCSX-Redux.app/Contents/MacOS/PCSX-Redux"),
        lua_bootstrap=tmp_path / "bootstrap.lua",
        run=True,
        stdout=True,
        lua_stdout=True,
        interpreter=True,
        debugger=True,
        testmode=True,
        portable_directory=tmp_path / "portable",
        bios=tmp_path / "bios.bin",
        iso=tmp_path / "game.cue",
    )
    assert build_pcsx_redux_args(options) == [
        str(options.executable),
        "-run",
        "-stdout",
        "-lua_stdout",
        "-interpreter",
        "-debugger",
        "-testmode",
        "-portable",
        str(tmp_path / "portable"),
        "-bios",
        str(tmp_path / "bios.bin"),
        "-iso",
        str(tmp_path / "game.cue"),
        "-dofile",
        str(tmp_path / "bootstrap.lua"),
    ]
    assert "-lua" not in build_pcsx_redux_args(options)


def test_argument_builder_omits_unrequested_bios_iso_and_testmode(tmp_path: Path) -> None:
    options = PCSXLaunchOptions(Path("pcsx-redux"), tmp_path / "bootstrap.lua", testmode=False)
    arguments = build_pcsx_redux_args(options)
    assert "-bios" not in arguments
    assert "-iso" not in arguments
    assert "-testmode" not in arguments


class NoopBridge:
    host = "127.0.0.1"
    port = 1234
    session_token = "token"
    connected = False

    def accept(self, timeout_seconds: float) -> None: del timeout_seconds
    def request(self, operation: str, payload: dict[str, object], timeout_seconds: float) -> dict[str, object]:
        del operation, payload, timeout_seconds
        return {}
    def drain_events(self) -> list[dict[str, object]]: return []
    def close(self) -> None: pass


def test_adapter_rejects_ambiguous_or_ui_save_state_format(tmp_path: Path) -> None:
    adapter = PCSXReduxAdapter(
        PCSXLaunchOptions(Path("pcsx-redux"), tmp_path / "bootstrap.lua"),
        NoopBridge(),  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="uncompressed"):
        adapter.load_state(tmp_path / "ui-state.gz")
