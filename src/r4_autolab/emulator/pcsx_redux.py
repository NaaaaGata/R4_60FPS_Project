from __future__ import annotations

import base64
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Any, Protocol

from ..models import BreakpointSpec, LaunchConfig, RegisterSnapshot


class BridgeTransport(Protocol):
    host: str
    port: int
    session_token: str

    @property
    def connected(self) -> bool: ...

    def accept(self, timeout_seconds: float) -> None: ...
    def request(self, operation: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]: ...
    def wait_for_events(
        self,
        predicate: Any,
        count: int,
        timeout_seconds: float,
    ) -> list[dict[str, Any]]: ...
    def drain_events(self) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class PCSXLaunchOptions:
    executable: Path
    lua_bootstrap: Path
    run: bool = True
    stdout: bool = True
    lua_stdout: bool = True
    interpreter: bool = True
    debugger: bool = True
    testmode: bool = False
    portable_directory: Path | None = None
    bios: Path | None = None
    iso: Path | None = None


def build_pcsx_redux_args(options: PCSXLaunchOptions) -> list[str]:
    """Build arguments using only flags documented by PCSX-Redux."""
    arguments = [str(options.executable)]
    if options.run:
        arguments.append("-run")
    if options.stdout:
        arguments.append("-stdout")
    if options.lua_stdout:
        arguments.append("-lua_stdout")
    if options.interpreter:
        arguments.append("-interpreter")
    if options.debugger:
        arguments.append("-debugger")
    if options.testmode:
        arguments.append("-testmode")
    if options.portable_directory is not None:
        arguments.extend(["-portable", str(options.portable_directory)])
    if options.bios is not None:
        arguments.extend(["-bios", str(options.bios)])
    if options.iso is not None:
        arguments.extend(["-iso", str(options.iso)])
    arguments.extend(["-dofile", str(options.lua_bootstrap)])
    return arguments


def discover_pcsx_redux(configured: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    environment = os.environ.get("R4_AUTOLAB_PCSX_REDUX")
    if environment:
        candidates.append(Path(environment).expanduser())
    if configured is not None:
        candidates.append(configured.expanduser())
    found = shutil.which("pcsx-redux") or shutil.which("PCSX-Redux")
    if found:
        candidates.append(Path(found))
    candidates.extend(
        [
            Path("/Applications/PCSX-Redux.app/Contents/MacOS/PCSX-Redux"),
            Path.home() / "Applications/PCSX-Redux.app/Contents/MacOS/PCSX-Redux",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def query_pcsx_redux_version(executable: Path, timeout_seconds: float = 5.0) -> dict[str, str]:
    result = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=True,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("PCSX-Redux version output is not a JSON object")
    return {str(key): str(item) for key, item in value.items()}


def local_architecture() -> str:
    return platform.machine()


class PCSXReduxAdapter:
    def __init__(self, options: PCSXLaunchOptions, bridge: BridgeTransport) -> None:
        self.options = options
        self.bridge = bridge
        self.process: subprocess.Popen[bytes] | None = None
        self.timeout_seconds = 5.0
        self._log_handle: Any = None
        self._process_lock: Any = None

    def _acquire_process_lock(self) -> None:
        lock_path = Path(tempfile.gettempdir()) / "r4-autolab-pcsx-redux.lock"
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.close()
            raise RuntimeError(
                "another R4 AutoLab PCSX-Redux process is active; wait for it to finish or stop it first"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        self._process_lock = handle

    def _release_process_lock(self) -> None:
        if self._process_lock is None:
            return
        fcntl.flock(self._process_lock.fileno(), fcntl.LOCK_UN)
        self._process_lock.close()
        self._process_lock = None

    def _request(self, operation: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.bridge.request(operation, payload or {}, self.timeout_seconds)

    def launch(self, config: LaunchConfig) -> object:
        if self.process is not None:
            raise RuntimeError("PCSX-Redux is already launched")
        self.timeout_seconds = config.timeout_seconds
        config.run_dir.mkdir(parents=True, exist_ok=True)
        portable = self.options.portable_directory or config.run_dir / "portable"
        portable.mkdir(parents=True, exist_ok=True)
        effective_options = PCSXLaunchOptions(
            executable=self.options.executable,
            lua_bootstrap=self.options.lua_bootstrap,
            run=self.options.run,
            stdout=self.options.stdout,
            lua_stdout=self.options.lua_stdout,
            interpreter=self.options.interpreter,
            debugger=self.options.debugger,
            testmode=self.options.testmode,
            portable_directory=portable,
            bios=self.options.bios,
            iso=self.options.iso,
        )
        environment = os.environ.copy()
        environment.update(
            {
                "R4_AUTOLAB_IPC_HOST": self.bridge.host,
                "R4_AUTOLAB_IPC_PORT": str(self.bridge.port),
                "R4_AUTOLAB_OUTPUT_DIR": str(config.run_dir.resolve()),
                "R4_AUTOLAB_SESSION_TOKEN": self.bridge.session_token,
                "R4_AUTOLAB_INTERPRETER": "1" if effective_options.interpreter else "0",
                "R4_AUTOLAB_DEBUGGER": "1" if effective_options.debugger else "0",
            }
        )
        self._acquire_process_lock()
        try:
            self._log_handle = (config.run_dir / "pcsx-redux.log").open("wb")
            self.process = subprocess.Popen(
                build_pcsx_redux_args(effective_options),
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                shell=False,
                env=environment,
                cwd=str(config.run_dir),
            )
        except Exception:
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None
            self._release_process_lock()
            raise
        return self.process

    def connect(self) -> None:
        if self.bridge.connected:
            return
        self.bridge.accept(self.timeout_seconds)

    def handshake(self) -> dict[str, Any]:
        return self._request("handshake", {"session_token": self.bridge.session_token})

    def load_state(self, state: Path) -> None:
        if state.suffix.lower() != ".rawstate":
            raise ValueError(
                "PCSX-Redux bridge accepts only explicitly uncompressed .rawstate files; "
                "UI-generated gzip save states are not accepted"
            )
        self._request("load_state", {"path": str(state.resolve()), "format": "raw-protobuf"})

    def create_save_state(self, state: Path) -> None:
        if state.suffix.lower() != ".rawstate":
            raise ValueError("raw save-state output must use the .rawstate extension")
        self._request("create_save_state", {"path": str(state.resolve()), "format": "raw-protobuf"})

    def run_vblanks(self, count: int) -> None:
        self._request("run_vblanks", {"count": count})
        self.bridge.wait_for_events(
            lambda event: event.get("event") == "vblank_target_reached",
            1,
            self.timeout_seconds,
        )

    def pause(self) -> None:
        self._request("pause")

    def resume(self) -> None:
        self._request("resume")

    def read_memory(self, address: int, size: int) -> bytes:
        result = self._request("read_memory", {"address": address, "size": size})
        data = base64.b64decode(str(result["data_base64"]), validate=True)
        if len(data) != size:
            raise ValueError(f"memory response size mismatch: expected {size}, got {len(data)}")
        return data

    def write_memory(self, address: int, data: bytes) -> None:
        self._request(
            "write_memory",
            {"address": address, "data_base64": base64.b64encode(data).decode("ascii")},
        )

    def set_breakpoint(self, spec: BreakpointSpec) -> str:
        result = self._request(
            "set_breakpoint",
            {"address": spec.address, "access": spec.access, "width": spec.width, "max_hits": spec.max_hits},
        )
        return str(result["breakpoint_id"])

    def clear_breakpoint(self, breakpoint_id: str) -> None:
        self._request("clear_breakpoint", {"breakpoint_id": breakpoint_id})

    def get_registers(self) -> RegisterSnapshot:
        result = self._request("get_registers")
        return RegisterSnapshot(
            int(result["pc"]),
            int(result["ra"]),
            int(result["sp"]),
            {str(key): int(value) for key, value in dict(result.get("gprs", {})).items()},
        )

    def get_cpu_cycles(self) -> int:
        return int(self._request("get_cpu_cycles")["cycles"])

    def get_vblank_count(self) -> int:
        return int(self._request("get_vblank_count")["count"])

    def configure_watches(self, watches: list[dict[str, Any]]) -> int:
        return int(self._request("configure_watches", {"watches": watches})["configured"])

    def set_pad_buttons(self, buttons: list[str]) -> list[str]:
        result = self._request("set_pad_buttons", {"buttons": buttons})
        return [str(value) for value in list(result["buttons"])]

    def clear_pad_buttons(self) -> int:
        return int(self._request("clear_pad_buttons")["cleared"])

    def capture_screenshot(self, path: Path) -> None:
        raw_path = path.with_suffix(".raw").resolve()
        metadata_path = path.with_suffix(".json").resolve()
        result = self._request("capture_screenshot", {"raw_path": str(raw_path)})
        metadata_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def capture_vram(self, path: Path) -> None:
        raise NotImplementedError("VRAM capture is outside Phase 3A")

    def export_gpu_log(self, path: Path) -> None:
        raise NotImplementedError("GPU log export is outside Phase 3A")

    def drain_events(self) -> list[dict[str, Any]]:
        return self.bridge.drain_events()

    def shutdown(self) -> None:
        shutdown_error: Exception | None = None
        try:
            try:
                if self.bridge.connected:
                    self._request("shutdown")
            except Exception as error:
                shutdown_error = error
            finally:
                self.bridge.close()
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            self.process = None
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None
        finally:
            self._release_process_lock()
        if shutdown_error is not None:
            raise shutdown_error

    def process_is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None
