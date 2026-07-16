from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
import struct
from typing import Iterator


SECTOR_SIZE = 2352
MODE2_DATA_OFFSET = 24
USER_DATA_SIZE = 2048


@dataclass(frozen=True)
class IsoEntry:
    path: str
    lba: int
    size: int
    is_directory: bool


@dataclass(frozen=True)
class PsxExecutableMetadata:
    disc_serial: str
    disc_executable_path: str
    extracted_path: str
    sha256: str
    size: int
    initial_pc: str
    global_pointer: str
    load_address: str
    payload_size: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def cue_bin_path(cue_path: Path) -> Path:
    text = cue_path.read_text(encoding="utf-8", errors="strict")
    match = re.search(r'^FILE\s+"([^"]+)"\s+BINARY$', text, re.MULTILINE | re.IGNORECASE)
    if not match:
        raise ValueError("CUE does not contain one quoted BINARY file")
    path = cue_path.parent / match.group(1)
    if not path.is_file():
        raise FileNotFoundError(path)
    if "MODE2/2352" not in text.upper():
        raise ValueError("only MODE2/2352 data tracks are supported")
    return path


class Mode2Iso9660:
    def __init__(self, bin_path: Path) -> None:
        self.bin_path = bin_path

    def _sector(self, lba: int) -> bytes:
        with self.bin_path.open("rb") as handle:
            handle.seek(lba * SECTOR_SIZE + MODE2_DATA_OFFSET)
            data = handle.read(USER_DATA_SIZE)
        if len(data) != USER_DATA_SIZE:
            raise ValueError(f"short sector read at LBA {lba}")
        return data

    def _extent(self, lba: int, size: int) -> bytes:
        sectors = (size + USER_DATA_SIZE - 1) // USER_DATA_SIZE
        return b"".join(self._sector(lba + index) for index in range(sectors))[:size]

    def _root(self) -> tuple[int, int]:
        descriptor = self._sector(16)
        if descriptor[:7] != b"\x01CD001\x01":
            raise ValueError("ISO9660 primary volume descriptor was not found")
        record = descriptor[156:]
        if not record or record[0] < 34:
            raise ValueError("invalid ISO9660 root directory record")
        return struct.unpack_from("<I", record, 2)[0], struct.unpack_from("<I", record, 10)[0]

    def _directory_records(self, lba: int, size: int, parent: str) -> Iterator[IsoEntry]:
        data = self._extent(lba, size)
        position = 0
        while position < len(data):
            length = data[position]
            if length == 0:
                position = ((position // USER_DATA_SIZE) + 1) * USER_DATA_SIZE
                continue
            record = data[position:position + length]
            if len(record) < 34:
                raise ValueError("truncated ISO9660 directory record")
            name_length = record[32]
            raw_name = record[33:33 + name_length]
            position += length
            if raw_name in {b"\x00", b"\x01"}:
                continue
            name = raw_name.decode("ascii", errors="strict").split(";", 1)[0]
            entry_path = f"{parent}/{name}" if parent else name
            yield IsoEntry(
                path=entry_path,
                lba=struct.unpack_from("<I", record, 2)[0],
                size=struct.unpack_from("<I", record, 10)[0],
                is_directory=bool(record[25] & 0x02),
            )

    def entries(self) -> list[IsoEntry]:
        root_lba, root_size = self._root()
        result: list[IsoEntry] = []

        def visit(lba: int, size: int, parent: str) -> None:
            for entry in self._directory_records(lba, size, parent):
                result.append(entry)
                if entry.is_directory:
                    visit(entry.lba, entry.size, entry.path)

        visit(root_lba, root_size, "")
        return result

    def read_file(self, path: str) -> bytes:
        normalized = path.replace("\\", "/").lstrip("/").upper()
        for entry in self.entries():
            if not entry.is_directory and entry.path.upper() == normalized:
                return self._extent(entry.lba, entry.size)
        raise FileNotFoundError(path)


def inspect_disc_executable(cue_path: Path, extraction_directory: Path) -> PsxExecutableMetadata:
    image = Mode2Iso9660(cue_bin_path(cue_path))
    system = image.read_file("SYSTEM.CNF").decode("ascii", errors="strict")
    match = re.search(r"BOOT\s*=\s*cdrom:\\?([^\r\n;]+(?:;\d+)?)", system, re.IGNORECASE)
    if not match:
        raise ValueError("SYSTEM.CNF does not contain a BOOT executable")
    disc_path = match.group(1).replace("\\", "/").split(";", 1)[0].lstrip("/")
    executable = image.read_file(disc_path)
    if len(executable) < 0x800 or not executable.startswith(b"PS-X EXE"):
        raise ValueError("boot file is not a PS-X EXE")
    extraction_directory.mkdir(parents=True, exist_ok=True)
    output = extraction_directory / Path(disc_path).name
    output.write_bytes(executable)
    serial = Path(disc_path).name.replace("_", "-").replace(".", "")
    return PsxExecutableMetadata(
        disc_serial=serial,
        disc_executable_path=disc_path,
        extracted_path=str(output.resolve()),
        sha256=hashlib.sha256(executable).hexdigest(),
        size=len(executable),
        initial_pc=f"0x{struct.unpack_from('<I', executable, 0x10)[0]:08X}",
        global_pointer=f"0x{struct.unpack_from('<I', executable, 0x14)[0]:08X}",
        load_address=f"0x{struct.unpack_from('<I', executable, 0x18)[0]:08X}",
        payload_size=struct.unpack_from("<I", executable, 0x1C)[0],
    )
