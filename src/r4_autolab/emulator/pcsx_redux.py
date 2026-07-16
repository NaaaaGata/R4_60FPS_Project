from __future__ import annotations

import base64
from pathlib import Path
import subprocess
from typing import Any, Protocol

from ..models import BreakpointSpec, LaunchConfig, RegisterSnapshot


class BridgeTransport(Protocol):
    def request(self, operation: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]: ...
    def drain_events(self) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


class PCSXReduxAdapter:
    """Explicit PCSX-Redux boundary; a tested transport must be supplied by deployment."""

    def __init__(self, executable: Path, bridge: BridgeTransport, lua_bootstrap: Path) -> None:
        self.executable = executable
        self.bridge = bridge
        self.lua_bootstrap = lua_bootstrap
        self.process: subprocess.Popen[bytes] | None = None
        self.timeout_seconds = 5.0

    def _request(self, operation: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.bridge.request(operation, payload or {}, self.timeout_seconds)

    def launch(self, config: LaunchConfig) -> object:
        if self.process is not None:
            raise RuntimeError("PCSX-Redux is already launched")
        self.timeout_seconds = config.timeout_seconds
        log = (config.run_dir / "pcsx-redux.log").open("wb")
        # CLI flags must be verified against the installed PCSX-Redux build before real use.
        self.process = subprocess.Popen(
            [str(self.executable), "-lua", str(self.lua_bootstrap)],
            stdout=log,
            stderr=subprocess.STDOUT,
            shell=False,
        )
        return self.process

    def load_state(self, state: Path) -> None:
        self._request("load_state", {"path": str(state)})

    def run_vblanks(self, count: int) -> None:
        self._request("run_vblanks", {"count": count})

    def pause(self) -> None:
        self._request("pause")

    def resume(self) -> None:
        self._request("resume")

    def read_memory(self, address: int, size: int) -> bytes:
        result = self._request("read_memory", {"address": address, "size": size})
        return base64.b64decode(str(result["data_base64"]), validate=True)

    def write_memory(self, address: int, data: bytes) -> None:
        self._request(
            "write_memory",
            {"address": address, "data_base64": base64.b64encode(data).decode("ascii")},
        )

    def set_breakpoint(self, spec: BreakpointSpec) -> str:
        result = self._request(
            "set_breakpoint",
            {"address": spec.address, "access": spec.access, "width": spec.width},
        )
        return str(result["breakpoint_id"])

    def clear_breakpoint(self, breakpoint_id: str) -> None:
        self._request("clear_breakpoint", {"breakpoint_id": breakpoint_id})

    def get_registers(self) -> RegisterSnapshot:
        result = self._request("get_registers")
        return RegisterSnapshot(
            int(result["pc"]), int(result["ra"]), int(result["sp"]),
            {str(k): int(v) for k, v in dict(result.get("gprs", {})).items()},
        )

    def capture_screenshot(self, path: Path) -> None:
        self._request("capture_screenshot", {"path": str(path)})

    def capture_vram(self, path: Path) -> None:
        self._request("capture_vram", {"path": str(path)})

    def export_gpu_log(self, path: Path) -> None:
        self._request("export_gpu_log", {"path": str(path)})

    def drain_events(self) -> list[dict[str, Any]]:
        return self.bridge.drain_events()

    def shutdown(self) -> None:
        try:
            self._request("shutdown")
        except Exception:
            pass
        self.bridge.close()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process = None

