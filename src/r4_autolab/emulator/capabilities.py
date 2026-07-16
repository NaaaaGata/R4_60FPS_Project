from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Any, Callable, Protocol

from ..models import LaunchConfig
from ..models import BreakpointSpec
from .pcsx_redux import PCSXReduxAdapter


class EventTransport(Protocol):
    def drain_events(self) -> list[dict[str, Any]]: ...
    def wait_for_events(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        count: int,
        timeout_seconds: float,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class CapabilityCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class CapabilityReport:
    created_at: str
    executable: str
    version: dict[str, str]
    architecture: str
    checks: list[CapabilityCheck]
    log_path: str

    @property
    def succeeded(self) -> bool:
        return not any(check.status == "FAIL" for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["succeeded"] = self.succeeded
        return value


class CapabilityRunner:
    READ_ADDRESS = 0x00000000
    READ_SIZE = 4
    SCRATCH_START = 0x1F800000
    SCRATCH_END = 0x1F800400

    def __init__(
        self,
        adapter: PCSXReduxAdapter,
        transport: EventTransport,
        run_dir: Path,
        *,
        executable: Path,
        version: dict[str, str],
        architecture: str,
        timeout_seconds: float,
        allow_scratch_write: bool = False,
        scratch_address: int | None = None,
        include_save_state_roundtrip: bool = False,
        include_breakpoint_smoke: bool = False,
    ) -> None:
        self.adapter = adapter
        self.transport = transport
        self.run_dir = run_dir
        self.executable = executable
        self.version = version
        self.architecture = architecture
        self.timeout_seconds = timeout_seconds
        self.allow_scratch_write = allow_scratch_write
        self.scratch_address = scratch_address
        self.include_save_state_roundtrip = include_save_state_roundtrip
        self.include_breakpoint_smoke = include_breakpoint_smoke
        self.checks: list[CapabilityCheck] = []
        self._launched = False
        self._connected = False

    def _pass(self, name: str, detail: str) -> None:
        self.checks.append(CapabilityCheck(name, "PASS", detail))

    def _fail(self, name: str, error: BaseException) -> None:
        self.checks.append(CapabilityCheck(name, "FAIL", f"{type(error).__name__}: {error}"))

    def _skip(self, name: str, detail: str) -> None:
        self.checks.append(CapabilityCheck(name, "SKIP", detail))

    def _attempt(self, name: str, action: Callable[[], str]) -> bool:
        try:
            self._pass(name, action())
            return True
        except Exception as error:
            self._fail(name, error)
            return False

    def _scratch_write(self) -> str:
        address = self.scratch_address
        if address is None:
            raise ValueError("no operator-confirmed scratch address was configured")
        width = 4
        if address % width or not self.SCRATCH_START <= address <= self.SCRATCH_END - width:
            raise ValueError("scratch address must be aligned inside 0x1F800000..0x1F8003FF")
        original = self.adapter.read_memory(address, width)
        replacement = bytes(byte ^ 0xA5 for byte in original)
        restored = False
        observed: bytes | None = None
        verification_error: Exception | None = None
        try:
            self.adapter.write_memory(address, replacement)
            observed = self.adapter.read_memory(address, width)
            if observed != replacement:
                raise RuntimeError("scratch write read-back mismatch")
        except Exception as error:
            verification_error = error
        finally:
            try:
                self.adapter.write_memory(address, original)
                restored = self.adapter.read_memory(address, width) == original
            except Exception:
                restored = False
        if not restored:
            raise RuntimeError(
                "scratch bytes could not be verified after restoration; "
                f"original={original.hex()} replacement={replacement.hex()} "
                f"observed={observed.hex() if observed is not None else 'unavailable'}"
            )
        if verification_error is not None:
            raise RuntimeError(
                f"{verification_error}; original={original.hex()} replacement={replacement.hex()} "
                f"observed={observed.hex() if observed is not None else 'unavailable'} "
                "restore_verified=true"
            ) from verification_error
        return f"restored 4 bytes at operator-confirmed scratch address 0x{address:08X}"

    def run(self) -> CapabilityReport:
        self.run_dir.mkdir(parents=True, exist_ok=False)
        log_path = self.run_dir / "pcsx-redux.log"
        read_only_ok = True
        try:
            if self._attempt(
                "launch",
                lambda: self._launch_detail(),
            ):
                self._launched = True
            else:
                read_only_ok = False

            if read_only_ok and self._attempt("ipc_connection", self._connect_detail):
                self._connected = True
            else:
                read_only_ok = False

            if read_only_ok:
                read_only_ok = self._attempt("protocol_handshake", self._handshake_detail)
            else:
                self._skip("protocol_handshake", "blocked by launch or IPC failure")

            if read_only_ok:
                read_only_ok = self._attempt("pause", self._pause_detail)
            else:
                self._skip("pause", "blocked by handshake failure")

            if read_only_ok:
                self.transport.drain_events()
                read_only_ok = self._attempt("resume", self._resume_detail)
            else:
                self._skip("resume", "blocked by pause failure")

            if read_only_ok:
                read_only_ok = self._attempt("vblank_events", self._vblank_detail)
            else:
                self._skip("vblank_events", "blocked by resume failure")

            if read_only_ok:
                # Stabilize read-only observations after proving execution can resume.
                read_only_ok = self._attempt("execution_counters", self._counter_detail)
            else:
                self._skip("execution_counters", "blocked by VBlank failure")

            if read_only_ok:
                read_only_ok = self._attempt("registers", self._register_detail)
            else:
                self._skip("registers", "blocked by execution counter failure")

            if read_only_ok:
                read_only_ok = self._attempt("memory_read", self._memory_detail)
            else:
                self._skip("memory_read", "blocked by register failure")

            if read_only_ok:
                read_only_ok = self._attempt("screenshot", self._screenshot_detail)
            else:
                self._skip("screenshot", "blocked by read-only memory failure")

            if not self.include_breakpoint_smoke:
                self._skip("breakpoint_smoke", "not requested")
            elif read_only_ok:
                read_only_ok = self._attempt("breakpoint_smoke", self._breakpoint_detail)
            else:
                self._skip("breakpoint_smoke", "read-only capability checks did not all pass")

            if not self.include_save_state_roundtrip:
                self._skip("save_state_roundtrip", "not requested")
            elif read_only_ok:
                read_only_ok = self._attempt("save_state_roundtrip", self._save_state_detail)
            else:
                self._skip("save_state_roundtrip", "read-only capability checks did not all pass")

            if not self.allow_scratch_write:
                self._skip("scratch_write", "not requested; pass --allow-scratch-write explicitly")
            elif not read_only_ok:
                self._skip("scratch_write", "read-only capability checks did not all pass")
            elif self.scratch_address is None:
                self._skip("scratch_write", "safe scratch location was not operator-confirmed")
            else:
                self._attempt("scratch_write", self._scratch_write)
        finally:
            if self._launched:
                self._attempt("shutdown", self._shutdown_detail)
                if self.adapter.process_is_alive():
                    self._fail("process_cleanup", RuntimeError("PCSX-Redux child process is still alive"))
                else:
                    self._pass("process_cleanup", "no PCSX-Redux child process remains")
            else:
                self._skip("shutdown", "PCSX-Redux was not launched")
                self._skip("process_cleanup", "PCSX-Redux was not launched")

        report = CapabilityReport(
            created_at=datetime.now(UTC).isoformat(),
            executable=str(self.executable),
            version=self.version,
            architecture=self.architecture,
            checks=self.checks,
            log_path=str(log_path),
        )
        (self.run_dir / "capabilities.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report

    def _launch_detail(self) -> str:
        self.adapter.launch(LaunchConfig("pcsx-capabilities", self.run_dir, self.timeout_seconds))
        return f"started PID {self.adapter.process.pid if self.adapter.process else 'unknown'}"

    def _connect_detail(self) -> str:
        self.adapter.connect()
        return "Lua client connected from 127.0.0.1"

    def _handshake_detail(self) -> str:
        value = self.adapter.handshake()
        if int(value.get("protocol_version", -1)) != 1:
            raise RuntimeError(f"unexpected protocol version: {value.get('protocol_version')}")
        if value.get("interpreter") is not True or value.get("debugger") is not True:
            raise RuntimeError("interpreter/debugger flags were not acknowledged by Lua host")
        return (
            f"protocol=1 lua={value.get('lua_version')} jit={value.get('jit_version')} "
            "interpreter=true debugger=true"
        )

    def _pause_detail(self) -> str:
        self.adapter.pause()
        return "pause request acknowledged"

    def _resume_detail(self) -> str:
        self.adapter.resume()
        return "resume request acknowledged"

    def _vblank_detail(self) -> str:
        events = self.transport.wait_for_events(
            lambda event: event.get("event") == "vblank",
            10,
            self.timeout_seconds,
        )
        indexes = [int(event["vblank_index"]) for event in events]
        if indexes != sorted(indexes) or len(set(indexes)) != len(indexes):
            raise RuntimeError(f"VBlank indexes are not strictly increasing: {indexes}")
        return f"received {len(events)} VBlank events ({indexes[0]}..{indexes[-1]})"

    def _register_detail(self) -> str:
        registers = self.adapter.get_registers()
        required = {"gp", "a0", "a1", "a2", "a3", "v0", "v1"}
        required.update(f"s{index}" for index in range(8))
        required.update(f"t{index}" for index in range(10))
        missing = sorted(required - registers.gprs.keys())
        if missing:
            raise RuntimeError("missing registers: " + ", ".join(missing))
        return f"PC=0x{registers.pc:08X} RA=0x{registers.ra:08X} SP=0x{registers.sp:08X}"

    def _counter_detail(self) -> str:
        self.adapter.pause()
        cycles = self.adapter.get_cpu_cycles()
        vblanks = self.adapter.get_vblank_count()
        if cycles < 0 or vblanks < 10:
            raise RuntimeError(f"invalid execution counters: cycles={cycles} vblanks={vblanks}")
        return f"cpu_cycles={cycles} vblank_count={vblanks}"

    def _memory_detail(self) -> str:
        data = self.adapter.read_memory(self.READ_ADDRESS, self.READ_SIZE)
        return f"read {len(data)} bytes at 0x{self.READ_ADDRESS:08X} through getMemoryAsFile"

    def _screenshot_detail(self) -> str:
        base = self.run_dir / "screenshot"
        self.adapter.capture_screenshot(base)
        raw = base.with_suffix(".raw")
        metadata = base.with_suffix(".json")
        if not raw.is_file() or raw.stat().st_size == 0 or not metadata.is_file():
            raise RuntimeError("screenshot raw data or metadata was not created")
        return f"raw={raw.name} bytes={raw.stat().st_size} metadata={metadata.name}"

    def _breakpoint_detail(self) -> str:
        # This address is in PS1 scratchpad, not game executable memory; the breakpoint is never resumed into.
        identifier = self.adapter.set_breakpoint(BreakpointSpec(self.SCRATCH_END - 4, "execute", 4))
        self.adapter.clear_breakpoint(identifier)
        return f"created and removed non-firing Exec breakpoint {identifier}"

    def _save_state_detail(self) -> str:
        state = self.run_dir / "roundtrip.rawstate"
        self.adapter.create_save_state(state)
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            if state.is_file() and state.stat().st_size > 0:
                break
            time.sleep(0.05)
        if not state.is_file() or state.stat().st_size == 0:
            raise RuntimeError("raw save state was not created before the timeout")
        self.adapter.load_state(state)
        return f"created and loaded raw-protobuf state ({state.stat().st_size} bytes)"

    def _shutdown_detail(self) -> str:
        self.adapter.shutdown()
        return "shutdown completed"
