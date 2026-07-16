from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from ..models import BreakpointSpec, LaunchConfig, RegisterSnapshot


_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeEmulator:
    """Deterministic adapter used by tests and the default dry run."""

    PATCH_ADDRESS = 0x80010000

    def __init__(self, *, crash_at_vblank: int | None = None) -> None:
        self.memory: dict[int, int] = {}
        self.events: list[dict[str, Any]] = []
        self.breakpoints: dict[str, BreakpointSpec] = {}
        self.running = False
        self.paused = False
        self.vblank = 0
        self.crash_at_vblank = crash_at_vblank
        self.scenario = ""
        self.run_dir: Path | None = None

    def launch(self, config: LaunchConfig) -> object:
        if self.running:
            raise RuntimeError("fake emulator is already running")
        self.running = True
        self.scenario = config.scenario
        self.run_dir = config.run_dir
        return {"pid": "fake", "scenario": self.scenario}

    def load_state(self, state: Path) -> None:
        if not self.running:
            raise RuntimeError("fake emulator is not running")
        if not state.exists():
            raise FileNotFoundError(state)

    def run_vblanks(self, count: int) -> None:
        if not self.running or self.paused:
            raise RuntimeError("fake emulator cannot run VBlanks in its current state")
        render_every_vblank = self.read_memory(self.PATCH_ADDRESS, 4) != b"\x00\x00\x00\x00"
        for _ in range(count):
            self.vblank += 1
            if self.crash_at_vblank is not None and self.vblank >= self.crash_at_vblank:
                self.running = False
                raise RuntimeError("injected fake emulator crash")
            physics_step = self.vblank // 2
            render_step = self.vblank if render_every_vblank else self.vblank // 2
            self.events.append(
                {
                    "protocol_version": 1,
                    "kind": "event",
                    "event": "vblank",
                    "sequence": self.vblank,
                    "monotonic_timestamp": self.vblank / 60.0,
                    "wall_clock_timestamp": f"fake+{self.vblank:06d}",
                    "vblank_index": self.vblank,
                    "emulated_frame_counter": render_step,
                    "pc": "0x80011000",
                    "ra": "0x80010FF0",
                    "sp": "0x801FFF00",
                    "gprs": {"a0": physics_step, "v0": render_step},
                    "breakpoint_cause": None,
                    "watch_values": {
                        "position": physics_step * 0.5,
                        "speed": 120.0,
                        "rpm": 5000.0,
                    },
                    "game_timer": self.vblank / 60.0,
                    "display_buffer": render_step % 2,
                    "gpu_hash": f"fake-gpu-{render_step:08d}",
                    "emulator_status": "running",
                    "dropped_event_count": 0,
                }
            )

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        if not self.running:
            raise RuntimeError("fake emulator is not running")
        self.paused = False

    def read_memory(self, address: int, size: int) -> bytes:
        return bytes(self.memory.get(address + offset, 0) for offset in range(size))

    def write_memory(self, address: int, data: bytes) -> None:
        if not self.running:
            raise RuntimeError("fake emulator is not running")
        for offset, byte in enumerate(data):
            self.memory[address + offset] = byte

    def set_breakpoint(self, spec: BreakpointSpec) -> str:
        identifier = f"fake-bp-{len(self.breakpoints) + 1}"
        self.breakpoints[identifier] = spec
        return identifier

    def clear_breakpoint(self, breakpoint_id: str) -> None:
        self.breakpoints.pop(breakpoint_id, None)

    def get_registers(self) -> RegisterSnapshot:
        return RegisterSnapshot(0x80011000, 0x80010FF0, 0x801FFF00, {"v0": self.vblank})

    def capture_screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_ONE_PIXEL_PNG)

    def capture_vram(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"FAKE-VRAM\n")

    def export_gpu_log(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fake gpu log\n", encoding="utf-8")

    def drain_events(self) -> list[dict[str, Any]]:
        result = list(self.events)
        self.events.clear()
        return result

    def shutdown(self) -> None:
        self.running = False
        self.paused = False

