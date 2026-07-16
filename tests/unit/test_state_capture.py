from pathlib import Path
from typing import Any

from r4_autolab.analysis.iso9660 import PsxExecutableMetadata
from r4_autolab.models import RegisterSnapshot
from r4_autolab.state_capture import (
    CaptureAssets,
    capture_state_artifacts,
    confirm_game_loaded,
    update_project_config,
)


def identity(executable: Path) -> PsxExecutableMetadata:
    return PsxExecutableMetadata(
        disc_serial="SLPS-01800",
        disc_executable_path="SLPS_018.00",
        extracted_path=str(executable),
        sha256="95a9dc1e81039d5a404091bf75bb1fb67c32f693faa04b629fb48073b2641775",
        size=4096,
        initial_pc="0x80010020",
        global_pointer="0x00000000",
        load_address="0x80010000",
        payload_size=0x1000,
    )


class FakeCaptureAdapter:
    def __init__(self) -> None:
        self.paused = True
        self.loaded: Path | None = None
        self.run_count = 0

    def resume(self) -> None: self.paused = False
    def pause(self) -> None: self.paused = True
    def run_vblanks(self, count: int) -> None: self.run_count += count
    def get_registers(self) -> RegisterSnapshot:
        return RegisterSnapshot(0x80010020, 0x80010030, 0x801FFF00, {"a0": 1})
    def get_vblank_count(self) -> int: return 321
    def get_cpu_cycles(self) -> int: return 123456
    def read_memory(self, address: int, size: int) -> bytes:
        return address.to_bytes(4, "little")[:size]
    def capture_screenshot(self, path: Path) -> None:
        path.with_suffix(".raw").write_bytes(b"\0\0" * 4)
        path.with_suffix(".json").write_text(
            '{"width": 2, "height": 2, "bits_per_pixel": 16, "size": 8}\n', encoding="utf-8"
        )
    def create_save_state(self, path: Path) -> None: path.write_bytes(b"raw-protobuf")
    def load_state(self, path: Path) -> None: self.loaded = path


def make_assets(tmp_path: Path) -> CaptureAssets:
    cue = tmp_path / "game.cue"
    bin_path = tmp_path / "game.bin"
    bios = tmp_path / "bios.bin"
    executable = tmp_path / "SLPS_018.00"
    cue.write_text('FILE "game.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")
    bin_path.write_bytes(b"disc")
    bios.write_bytes(b"bios")
    executable.write_bytes(b"PS-X EXE")
    return CaptureAssets(cue, bin_path, bios, executable, identity(executable))


def test_capture_state_artifacts_pauses_and_writes_complete_metadata(tmp_path: Path) -> None:
    adapter = FakeCaptureAdapter()
    assets = make_assets(tmp_path)
    waited = False

    def enter() -> str:
        nonlocal waited
        waited = True
        return ""

    metadata = capture_state_artifacts(
        adapter,  # type: ignore[arg-type]
        tmp_path,
        "race-straight",
        assets,
        {"changeset": "test-build"},
        wait_for_enter=enter,
        timeout_seconds=1.0,
    )
    assert waited
    assert adapter.paused
    assert adapter.loaded == tmp_path / "race_straight.rawstate"
    assert metadata["serial"] == "SLPS-01800"
    assert metadata["source_hashes_unchanged"] is True
    assert (tmp_path / "race_straight.state.json").is_file()
    assert (tmp_path / "race_straight.raw").is_file()


def test_confirm_game_loaded_accepts_pc_in_verified_payload(tmp_path: Path) -> None:
    adapter = FakeCaptureAdapter()
    result = confirm_game_loaded(adapter, identity(tmp_path / "exe"), 1.0)  # type: ignore[arg-type]
    assert result.pc == 0x80010020
    assert adapter.run_count == 60


def test_update_project_config_uses_relative_private_paths(tmp_path: Path) -> None:
    config = tmp_path / "config/project.toml"
    config.parent.mkdir()
    source = Path(__file__).resolve().parents[2] / "config/project.example.toml"
    config.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    assets = make_assets(tmp_path)
    state = tmp_path / "states/race.rawstate"
    state.parent.mkdir()
    state.write_bytes(b"state")
    pcsx = tmp_path / "tools/pcsx-redux"
    pcsx.parent.mkdir()
    pcsx.write_bytes(b"exe")
    update_project_config(config, tmp_path, assets, state, pcsx)
    text = config.read_text(encoding="utf-8")
    assert 'mode = "real"' in text
    assert 'save_state = "states/race.rawstate"' in text
    assert 'disc_path = "game.cue"' in text
    assert 'scenario = "race-straight"' in text
    assert "vblanks = 120" in text
