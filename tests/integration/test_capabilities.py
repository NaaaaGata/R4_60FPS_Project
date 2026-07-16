from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from r4_autolab.emulator.capabilities import CapabilityRunner
from r4_autolab.models import RegisterSnapshot


class FakeCapabilityTransport:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def drain_events(self) -> list[dict[str, Any]]:
        result = list(self.events)
        self.events.clear()
        return result

    def wait_for_events(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        count: int,
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        del timeout_seconds
        values = [
            {"kind": "event", "event": "vblank", "vblank_index": index}
            for index in range(1, count + 1)
        ]
        return [value for value in values if predicate(value)]


class FakeCapabilityAdapter:
    def __init__(self, *, memory_fails: bool = False) -> None:
        self.process: Any = None
        self.alive = False
        self.memory = bytearray(0x400)
        self.memory_fails = memory_fails
        self.paused = False
        self.fail_replacement_read = False
        self.write_calls = 0
        self.breakpoints: set[str] = set()

    def launch(self, config: object) -> object:
        del config
        self.process = SimpleNamespace(pid=1234)
        self.alive = True
        return self.process

    def connect(self) -> None: pass
    def handshake(self) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            "lua_version": "Lua 5.1",
            "jit_version": "LuaJIT test",
            "interpreter": True,
            "debugger": True,
        }
    def pause(self) -> None: self.paused = True
    def resume(self) -> None: self.paused = False

    def get_registers(self) -> RegisterSnapshot:
        names = {"gp", "a0", "a1", "a2", "a3", "v0", "v1"}
        names.update(f"s{index}" for index in range(8))
        names.update(f"t{index}" for index in range(10))
        return RegisterSnapshot(1, 2, 3, {name: 0 for name in names})

    def get_cpu_cycles(self) -> int: return 12345
    def get_vblank_count(self) -> int: return 10

    def read_memory(self, address: int, size: int) -> bytes:
        if self.memory_fails:
            raise RuntimeError("injected memory failure")
        if address == 0:
            return b"\0" * size
        offset = address - CapabilityRunner.SCRATCH_START
        if self.fail_replacement_read and self.write_calls == 1:
            return b"\xff" * size
        return bytes(self.memory[offset:offset + size])

    def write_memory(self, address: int, data: bytes) -> None:
        self.write_calls += 1
        offset = address - CapabilityRunner.SCRATCH_START
        self.memory[offset:offset + len(data)] = data

    def capture_screenshot(self, path: Path) -> None:
        path.with_suffix(".raw").write_bytes(b"pixels")
        path.with_suffix(".json").write_text("{}", encoding="utf-8")

    def set_breakpoint(self, spec: object) -> str:
        del spec
        self.breakpoints.add("bp-test")
        return "bp-test"

    def clear_breakpoint(self, identifier: str) -> None:
        self.breakpoints.remove(identifier)

    def create_save_state(self, path: Path) -> None:
        path.write_bytes(b"raw-state")

    def load_state(self, path: Path) -> None:
        assert path.read_bytes() == b"raw-state"

    def shutdown(self) -> None:
        self.alive = False
        self.process = None

    def process_is_alive(self) -> bool: return self.alive


def test_capability_runner_completes_read_only_path(tmp_path: Path) -> None:
    adapter = FakeCapabilityAdapter()
    report = CapabilityRunner(
        adapter,  # type: ignore[arg-type]
        FakeCapabilityTransport(),
        tmp_path / "capability",
        executable=Path("pcsx-redux"),
        version={"version": "test"},
        architecture="arm64",
        timeout_seconds=1,
    ).run()
    statuses = {check.name: check.status for check in report.checks}
    assert report.succeeded
    assert statuses["memory_read"] == "PASS"
    assert statuses["scratch_write"] == "SKIP"
    assert statuses["process_cleanup"] == "PASS"
    assert (tmp_path / "capability/capabilities.json").exists()


def test_capability_runner_skips_later_checks_after_read_failure(tmp_path: Path) -> None:
    adapter = FakeCapabilityAdapter(memory_fails=True)
    report = CapabilityRunner(
        adapter,  # type: ignore[arg-type]
        FakeCapabilityTransport(),
        tmp_path / "capability",
        executable=Path("pcsx-redux"),
        version={},
        architecture="arm64",
        timeout_seconds=1,
        allow_scratch_write=True,
        scratch_address=CapabilityRunner.SCRATCH_START,
    ).run()
    statuses = {check.name: check.status for check in report.checks}
    assert not report.succeeded
    assert statuses["memory_read"] == "FAIL"
    assert statuses["screenshot"] == "SKIP"
    assert statuses["scratch_write"] == "SKIP"
    assert statuses["shutdown"] == "PASS"


def test_capability_runner_restores_operator_confirmed_scratch(tmp_path: Path) -> None:
    adapter = FakeCapabilityAdapter()
    before = bytes(adapter.memory)
    report = CapabilityRunner(
        adapter,  # type: ignore[arg-type]
        FakeCapabilityTransport(),
        tmp_path / "capability",
        executable=Path("pcsx-redux"),
        version={},
        architecture="arm64",
        timeout_seconds=1,
        allow_scratch_write=True,
        scratch_address=CapabilityRunner.SCRATCH_START,
    ).run()
    assert next(check for check in report.checks if check.name == "scratch_write").status == "PASS"
    assert bytes(adapter.memory) == before


def test_capability_runner_attempts_restore_after_scratch_verification_error(tmp_path: Path) -> None:
    adapter = FakeCapabilityAdapter()
    adapter.fail_replacement_read = True
    before = bytes(adapter.memory)
    report = CapabilityRunner(
        adapter,  # type: ignore[arg-type]
        FakeCapabilityTransport(),
        tmp_path / "capability",
        executable=Path("pcsx-redux"),
        version={},
        architecture="arm64",
        timeout_seconds=1,
        allow_scratch_write=True,
        scratch_address=CapabilityRunner.SCRATCH_START,
    ).run()
    assert next(check for check in report.checks if check.name == "scratch_write").status == "FAIL"
    assert adapter.write_calls == 2
    assert bytes(adapter.memory) == before


def test_capability_runner_extended_read_only_smokes(tmp_path: Path) -> None:
    adapter = FakeCapabilityAdapter()
    report = CapabilityRunner(
        adapter,  # type: ignore[arg-type]
        FakeCapabilityTransport(),
        tmp_path / "capability",
        executable=Path("pcsx-redux"),
        version={},
        architecture="arm64",
        timeout_seconds=1,
        include_save_state_roundtrip=True,
        include_breakpoint_smoke=True,
    ).run()
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["breakpoint_smoke"] == "PASS"
    assert statuses["save_state_roundtrip"] == "PASS"
    assert adapter.breakpoints == set()
