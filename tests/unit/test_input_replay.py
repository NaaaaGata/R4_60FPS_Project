from pathlib import Path

import pytest

from r4_autolab.input_replay import (
    InputScenario,
    evaluate_replay_attempts,
    load_input_scenarios,
    replay_input_scenario,
)
from r4_autolab.models import RegisterSnapshot


class FakeInputAdapter:
    def __init__(self, *, fail_run: bool = False) -> None:
        self.vblank = 0
        self.buttons: list[str] = []
        self.clear_calls = 0
        self.fail_run = fail_run

    def pause(self) -> None: pass
    def load_state(self, state: Path) -> None:
        assert state.is_file()
        self.vblank = 0
    def set_pad_buttons(self, buttons: list[str]) -> list[str]:
        self.buttons = sorted(buttons)
        return self.buttons
    def clear_pad_buttons(self) -> int:
        count = len(self.buttons)
        self.buttons = []
        self.clear_calls += 1
        return count
    def run_vblanks(self, count: int) -> None:
        if self.fail_run:
            raise RuntimeError("injected replay failure")
        self.vblank += count
    def get_registers(self) -> RegisterSnapshot:
        return RegisterSnapshot(0x80010000, 0x80010010, 0x801FFF00, {"a0": self.vblank})
    def get_vblank_count(self) -> int: return self.vblank
    def get_cpu_cycles(self) -> int: return self.vblank * 100
    def read_memory(self, address: int, size: int) -> bytes:
        del address
        return self.vblank.to_bytes(4, "little")[:size]
    def capture_screenshot(self, path: Path) -> None:
        value = (self.vblank + len(self.buttons)) & 0xFF
        path.with_suffix(".raw").write_bytes(bytes([value, 0]) * 4)
        path.with_suffix(".json").write_text(
            '{"width":2,"height":2,"bits_per_pixel":16,"size":8}\n', encoding="utf-8"
        )


def test_example_scenarios_have_all_required_names() -> None:
    root = Path(__file__).resolve().parents[2]
    scenarios = load_input_scenarios(root / "config/input_scenarios.example.json")
    assert set(scenarios) == {
        "neutral-120",
        "accelerate-straight-600",
        "steer-left-300",
        "steer-right-300",
        "accelerate-and-steer-600",
    }
    assert len({scenario.sha256 for scenario in scenarios.values()}) == 5


def test_replay_is_vblank_bounded_and_releases_input(tmp_path: Path) -> None:
    state = tmp_path / "state.rawstate"
    state.write_bytes(b"state")
    adapter = FakeInputAdapter()
    scenario = InputScenario("short", 120, ("CROSS",))
    report = replay_input_scenario(adapter, state, scenario, tmp_path / "replay", sample_every=60)
    assert [sample["relative_vblank"] for sample in report["samples"]] == [0, 60, 120]
    assert report["released_override_count"] == 1
    assert adapter.buttons == []
    assert evaluate_replay_attempts([report, report, report], 3)[0] == "PASS"


def test_replay_releases_input_after_execution_error(tmp_path: Path) -> None:
    state = tmp_path / "state.rawstate"
    state.write_bytes(b"state")
    adapter = FakeInputAdapter(fail_run=True)
    with pytest.raises(RuntimeError, match="injected"):
        replay_input_scenario(
            adapter,
            state,
            InputScenario("short", 60, ("LEFT",)),
            tmp_path / "replay",
            sample_every=60,
        )
    assert adapter.buttons == []
    assert adapter.clear_calls == 2


def test_scenario_loader_rejects_contradictory_directions(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        '{"protocol_version":1,"scenarios":[{"name":"bad","vblanks":1,"buttons":["LEFT","RIGHT"]}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="contradictory"):
        load_input_scenarios(path)
