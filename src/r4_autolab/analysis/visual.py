from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VisualStats:
    width: int
    height: int
    bits_per_pixel: int
    byte_count: int
    expected_byte_count: int
    valid_size: bool
    black_pixel_ratio: float
    extreme_pixel_ratio: float
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_raw_screenshot(raw_path: Path, metadata_path: Path) -> VisualStats:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    width = int(metadata["width"])
    height = int(metadata["height"])
    bits = int(metadata["bits_per_pixel"])
    if width <= 0 or height <= 0 or bits not in {16, 24}:
        raise ValueError("unsupported screenshot metadata")
    data = raw_path.read_bytes()
    bytes_per_pixel = bits // 8
    expected = width * height * bytes_per_pixel
    black = 0
    extreme = 0
    pixels = max(1, width * height)
    if bits == 24:
        for offset in range(0, min(len(data), expected), 3):
            pixel = data[offset:offset + 3]
            if len(pixel) < 3:
                break
            if max(pixel) <= 3:
                black += 1
            if min(pixel) <= 3 or max(pixel) >= 252:
                extreme += 1
    else:
        for offset in range(0, min(len(data), expected), 2):
            if offset + 1 >= len(data):
                break
            value = data[offset] | (data[offset + 1] << 8)
            red, green, blue = value & 31, (value >> 5) & 31, (value >> 10) & 31
            if max(red, green, blue) == 0:
                black += 1
            if min(red, green, blue) == 0 or max(red, green, blue) == 31:
                extreme += 1
    return VisualStats(
        width=width,
        height=height,
        bits_per_pixel=bits,
        byte_count=len(data),
        expected_byte_count=expected,
        valid_size=len(data) == expected,
        black_pixel_ratio=black / pixels,
        extreme_pixel_ratio=extreme / pixels,
        sha256=hashlib.sha256(data).hexdigest(),
    )
