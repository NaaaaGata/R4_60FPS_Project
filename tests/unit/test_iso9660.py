from pathlib import Path
import struct

from r4_autolab.analysis.iso9660 import MODE2_DATA_OFFSET, SECTOR_SIZE, inspect_disc_executable


def record(name: bytes, lba: int, size: int, directory: bool = False) -> bytes:
    length = 33 + len(name) + (1 if len(name) % 2 == 0 else 0)
    value = bytearray(length)
    value[0] = length
    struct.pack_into("<I", value, 2, lba)
    struct.pack_into(">I", value, 6, lba)
    struct.pack_into("<I", value, 10, size)
    struct.pack_into(">I", value, 14, size)
    value[25] = 2 if directory else 0
    value[28:32] = b"\x01\0\0\x01"
    value[32] = len(name)
    value[33:33 + len(name)] = name
    return bytes(value)


def put_sector(image: bytearray, lba: int, data: bytes) -> None:
    start = lba * SECTOR_SIZE + MODE2_DATA_OFFSET
    image[start:start + len(data)] = data


def test_extracts_boot_executable_from_mode2_iso(tmp_path: Path) -> None:
    image = bytearray(SECTOR_SIZE * 24)
    pvd = bytearray(2048)
    pvd[:7] = b"\x01CD001\x01"
    root = record(b"\0", 20, 2048, True)
    pvd[156:156 + len(root)] = root
    put_sector(image, 16, pvd)
    system = b"BOOT = cdrom:\\SLPS_018.00;1\r\n"
    executable = bytearray(0x800)
    executable[:8] = b"PS-X EXE"
    struct.pack_into("<IIII", executable, 0x10, 0x80010000, 0, 0x80010000, 0)
    directory = b"".join(
        [
            record(b"\0", 20, 2048, True),
            record(b"\1", 20, 2048, True),
            record(b"SYSTEM.CNF;1", 21, len(system)),
            record(b"SLPS_018.00;1", 22, len(executable)),
        ]
    )
    put_sector(image, 20, directory)
    put_sector(image, 21, system)
    put_sector(image, 22, executable)
    bin_path = tmp_path / "disc.bin"
    bin_path.write_bytes(image)
    cue = tmp_path / "disc.cue"
    cue.write_text('FILE "disc.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")
    metadata = inspect_disc_executable(cue, tmp_path / "private")
    assert metadata.disc_serial == "SLPS-01800"
    assert metadata.initial_pc == "0x80010000"
    assert Path(metadata.extracted_path).read_bytes() == executable
