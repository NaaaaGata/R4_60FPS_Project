from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import struct
from typing import Callable


PS1_RAM_SIZE = 0x200000
DMA_TERMINATOR = 0xFFFFFF


def ps1_ram_physical(address: int) -> int:
    if 0 <= address < PS1_RAM_SIZE:
        return address
    if 0x80000000 <= address < 0x80200000:
        return address - 0x80000000
    if 0xA0000000 <= address < 0xA0200000:
        return address - 0xA0000000
    raise ValueError(f"GPU pointer is outside PS1 RAM: 0x{address:08X}")


def ps1_ram_virtual(physical: int) -> int:
    if not 0 <= physical < PS1_RAM_SIZE:
        raise ValueError(f"GPU physical pointer is outside PS1 RAM: 0x{physical:06X}")
    return 0x80000000 | physical


@dataclass(frozen=True)
class GpuListNode:
    address: int
    command_words: int
    next_pointer: int


@dataclass(frozen=True)
class GpuListSnapshot:
    root: int
    status: str
    node_count: int
    command_words: int
    bytes_read: int
    sha256: str
    content_sha256: str
    nodes: tuple[GpuListNode, ...]
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["root"] = f"0x{self.root:08X}"
        preview = self.nodes if len(self.nodes) <= 16 else self.nodes[:8] + self.nodes[-8:]
        value.pop("nodes", None)
        value["node_preview"] = [
            {
                "address": f"0x{node.address:08X}",
                "command_words": node.command_words,
                "next_pointer": f"0x{node.next_pointer:06X}",
            }
            for node in preview
        ]
        value["node_preview_truncated"] = len(preview) != len(self.nodes)
        return value


MemoryReader = Callable[[int, int], bytes]


def hash_gpu_linked_list(
    read_memory: MemoryReader,
    root: int,
    *,
    max_nodes: int = 4096,
    max_bytes: int = 1024 * 1024,
) -> GpuListSnapshot:
    if not 1 <= max_nodes <= 4096:
        raise ValueError("max_nodes must be between 1 and 4096")
    if not 4 <= max_bytes <= 1024 * 1024:
        raise ValueError("max_bytes must be between 4 and 1048576")
    current = ps1_ram_physical(root)
    visited: set[int] = set()
    nodes: list[GpuListNode] = []
    digest = hashlib.sha256()
    content_digest = hashlib.sha256()
    total_bytes = 0
    command_words = 0
    status = "terminator"
    detail: str | None = None

    while True:
        if current in visited:
            status = "loop"
            detail = f"linked-list loop at 0x{current:06X}"
            break
        if len(nodes) >= max_nodes:
            status = "max_nodes"
            detail = f"node limit {max_nodes} reached"
            break
        if current > PS1_RAM_SIZE - 4:
            status = "invalid_pointer"
            detail = f"header pointer outside PS1 RAM: 0x{current:06X}"
            break
        if total_bytes + 4 > max_bytes:
            status = "max_bytes"
            detail = f"byte limit {max_bytes} reached before header"
            break

        virtual = ps1_ram_virtual(current)
        header = read_memory(virtual, 4)
        if len(header) != 4:
            raise ValueError("short GPU linked-list header read")
        word = int.from_bytes(header, "little")
        count = word >> 24
        next_pointer = word & DMA_TERMINATOR
        payload_size = count * 4
        if current + 4 + payload_size > PS1_RAM_SIZE:
            status = "invalid_payload"
            detail = f"node payload leaves PS1 RAM at 0x{current:06X}"
            break
        if total_bytes + 4 + payload_size > max_bytes:
            status = "max_bytes"
            detail = f"byte limit {max_bytes} reached at 0x{current:06X}"
            break

        payload = read_memory(virtual + 4, payload_size) if payload_size else b""
        if len(payload) != payload_size:
            raise ValueError("short GPU linked-list payload read")
        digest.update(struct.pack("<I", current))
        digest.update(header)
        digest.update(payload)
        content_digest.update(bytes([count]))
        content_digest.update(payload)
        visited.add(current)
        nodes.append(GpuListNode(virtual, count, next_pointer))
        total_bytes += 4 + payload_size
        command_words += count
        if next_pointer == DMA_TERMINATOR:
            break
        if next_pointer >= PS1_RAM_SIZE:
            status = "invalid_pointer"
            detail = f"next pointer outside PS1 RAM: 0x{next_pointer:06X}"
            break
        current = next_pointer

    return GpuListSnapshot(
        root=root,
        status=status,
        node_count=len(nodes),
        command_words=command_words,
        bytes_read=total_bytes,
        sha256=digest.hexdigest(),
        content_sha256=content_digest.hexdigest(),
        nodes=tuple(nodes),
        detail=detail,
    )


@dataclass(frozen=True)
class DisplayEnvironment:
    display_x: int
    display_y: int
    width: int
    height: int
    screen_x: int
    screen_y: int
    screen_width: int
    screen_height: int
    interlace: int
    rgb24: int

    @property
    def buffer_id(self) -> str:
        return f"display:{self.display_x},{self.display_y}:{self.width}x{self.height}"


@dataclass(frozen=True)
class DrawEnvironment:
    clip_x: int
    clip_y: int
    clip_width: int
    clip_height: int
    offset_x: int
    offset_y: int

    @property
    def buffer_id(self) -> str:
        return f"draw:{self.clip_x},{self.clip_y}:{self.clip_width}x{self.clip_height}"


def parse_display_environment(data: bytes) -> DisplayEnvironment:
    if len(data) < 20:
        raise ValueError("DISPENV requires 20 bytes")
    values = struct.unpack_from("<8h", data)
    return DisplayEnvironment(
        values[0], values[1], values[2], values[3],
        values[4], values[5], values[6], values[7],
        data[16], data[17],
    )


def parse_draw_environment(data: bytes) -> DrawEnvironment:
    if len(data) < 12:
        raise ValueError("DRAWENV requires 12 bytes")
    values = struct.unpack_from("<6h", data)
    return DrawEnvironment(values[0], values[1], values[2], values[3], values[4], values[5])


def combined_gpu_hash(snapshots: list[GpuListSnapshot], *, content_only: bool = False) -> str:
    digest = hashlib.sha256()
    for snapshot in snapshots:
        if not content_only:
            digest.update(snapshot.root.to_bytes(4, "little"))
        digest.update(bytes.fromhex(snapshot.content_sha256 if content_only else snapshot.sha256))
    return digest.hexdigest()
