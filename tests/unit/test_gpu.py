from __future__ import annotations

import struct

import pytest

from r4_autolab.analysis.gpu import (
    combined_gpu_hash,
    hash_gpu_linked_list,
    parse_display_environment,
    parse_draw_environment,
    ps1_ram_physical,
)
from r4_autolab.gpu_trace import COMMAND_ARENA_SIZE, arena_memory_reader


def memory_reader(memory: bytearray):
    def read(address: int, size: int) -> bytes:
        offset = ps1_ram_physical(address)
        return bytes(memory[offset : offset + size])

    return read


def write_node(memory: bytearray, offset: int, commands: list[int], next_pointer: int) -> None:
    struct.pack_into("<I", memory, offset, len(commands) << 24 | next_pointer)
    for index, command in enumerate(commands):
        struct.pack_into("<I", memory, offset + 4 + index * 4, command)


def test_hashes_bounded_gpu_linked_list() -> None:
    memory = bytearray(0x200000)
    write_node(memory, 0x100, [0xE1000400], 0x200)
    write_node(memory, 0x200, [0x20010203, 4], 0xFFFFFF)
    result = hash_gpu_linked_list(memory_reader(memory), 0x80000100)
    assert result.status == "terminator"
    assert result.node_count == 2
    assert result.command_words == 3
    assert result.bytes_read == 20
    assert len(result.sha256) == 64
    assert combined_gpu_hash([result]) == combined_gpu_hash([result])


@pytest.mark.parametrize("address", [0x80200000, 0xA0200000, 0x1F801810, -1])
def test_rejects_gpu_root_outside_ps1_ram(address: int) -> None:
    with pytest.raises(ValueError, match="outside PS1 RAM"):
        hash_gpu_linked_list(lambda _address, size: bytes(size), address)


def test_detects_linked_list_loop() -> None:
    memory = bytearray(0x200000)
    write_node(memory, 0x100, [], 0x200)
    write_node(memory, 0x200, [], 0x100)
    result = hash_gpu_linked_list(memory_reader(memory), 0x80000100)
    assert result.status == "loop"
    assert result.node_count == 2


def test_enforces_maximum_nodes() -> None:
    memory = bytearray(0x200000)
    write_node(memory, 0x100, [], 0x200)
    write_node(memory, 0x200, [], 0x300)
    result = hash_gpu_linked_list(memory_reader(memory), 0x80000100, max_nodes=1)
    assert result.status == "max_nodes"
    assert result.node_count == 1


def test_enforces_maximum_bytes_before_payload_read() -> None:
    memory = bytearray(0x200000)
    write_node(memory, 0x100, [1, 2], 0xFFFFFF)
    result = hash_gpu_linked_list(memory_reader(memory), 0x80000100, max_bytes=8)
    assert result.status == "max_bytes"
    assert result.node_count == 0


def test_rejects_payload_crossing_ram_boundary() -> None:
    memory = bytearray(0x200000)
    struct.pack_into("<I", memory, 0x1FFFFC, 1 << 24 | 0xFFFFFF)
    result = hash_gpu_linked_list(memory_reader(memory), 0x801FFFFC)
    assert result.status == "invalid_payload"


def test_parses_display_and_draw_buffer_models() -> None:
    display = parse_display_environment(struct.pack("<8h4B", 0, 240, 320, 240, 0, 0, 320, 240, 0, 0, 0, 0))
    draw = parse_draw_environment(struct.pack("<6h", 0, 0, 320, 240, 0, 0))
    assert display.buffer_id == "display:0,240:320x240"
    assert display.interlace == 0
    assert draw.buffer_id == "draw:0,0:320x240"


def test_command_arena_reader_rejects_out_of_arena_pointer() -> None:
    base = 0x800AD8D0
    reader = arena_memory_reader(base, bytes(COMMAND_ARENA_SIZE))
    assert reader(base + 4, 4) == b"\0" * 4
    with pytest.raises(ValueError, match="leaves command arena"):
        reader(base - 4, 4)
    with pytest.raises(ValueError, match="leaves command arena"):
        reader(base + COMMAND_ARENA_SIZE - 2, 4)
