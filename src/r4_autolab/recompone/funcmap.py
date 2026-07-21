from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


_SYMBOL = re.compile(r"[^A-Za-z0-9_]")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FuncMapConversion:
    source_sha256: str
    output_sha256: str
    payload_start: str
    payload_size: int
    function_count: int
    renamed_symbols: int
    split_body_functions: int
    omitted_body_ranges: int
    omitted_invalid_functions: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _address(value: Any, field: str) -> int:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a hexadecimal string")
    try:
        result = int(value, 0)
    except ValueError as error:
        raise ValueError(f"{field} must be a hexadecimal string") from error
    if result < 0 or result > 0xFFFFFFFF:
        raise ValueError(f"{field} is outside the 32-bit address space")
    return result


def _payload(value: dict[str, Any], block_name: str | None) -> tuple[int, int]:
    blocks = value.get("memory_blocks")
    if not isinstance(blocks, list):
        raise ValueError("Ghidra export is missing memory_blocks")
    candidates = [item for item in blocks if isinstance(item, dict)]
    if block_name is not None:
        candidates = [item for item in candidates if item.get("name") == block_name]
    else:
        preferred = [item for item in candidates if item.get("name") in {"R4_PAYLOAD", "R4_OVERLAY"}]
        candidates = preferred or candidates
    if len(candidates) != 1:
        raise ValueError("exactly one payload memory block must be selected")
    block = candidates[0]
    start = _address(block.get("start"), "memory block start")
    size = block.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("memory block size must be positive")
    if start + size > 0x100000000:
        raise ValueError("memory block overflows the 32-bit address space")
    return start, size


def _normalized_name(raw: Any, address: int) -> str:
    name = str(raw).strip()
    name = _SYMBOL.sub("_", name)
    if not name:
        name = f"FUN_{address:08X}"
    if name[0].isdigit():
        name = "FUN_" + name
    return name


def convert_ghidra_export(
    source: Path,
    output: Path,
    *,
    block_name: str | None = None,
    exclude_invalid_functions: bool = False,
) -> FuncMapConversion:
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Ghidra export must be a JSON object")
    source_sha256 = str(value.get("input_sha256", ""))
    if _SHA256.fullmatch(source_sha256) is None:
        raise ValueError("Ghidra export input_sha256 is invalid")
    if str(value.get("language_id", "")) != "MIPS:LE:32:default":
        raise ValueError("Ghidra export is not MIPS little-endian")
    payload_start, payload_size = _payload(value, block_name)
    payload_end = payload_start + payload_size
    raw_functions = value.get("functions")
    if not isinstance(raw_functions, list):
        raise ValueError("Ghidra export functions must be an array")
    entries: list[tuple[int, int, str]] = []
    split_bodies = 0
    omitted_ranges = 0
    omitted_invalid = 0
    for index, item in enumerate(raw_functions):
        if not isinstance(item, dict):
            raise ValueError(f"functions[{index}] must be an object")
        entry = _address(item.get("entry"), f"functions[{index}].entry")
        range_count_value = item.get("body_range_count", 1)
        if isinstance(range_count_value, bool) or not isinstance(range_count_value, int) or range_count_value <= 0:
            raise ValueError(f"functions[{index}].body_range_count is invalid")
        if "contiguous_end" in item:
            start = _address(item.get("contiguous_start"), f"functions[{index}].contiguous_start")
            end = _address(item.get("contiguous_end"), f"functions[{index}].contiguous_end")
        else:
            start = _address(item.get("start"), f"functions[{index}].start")
            end = _address(item.get("end"), f"functions[{index}].end")
        if range_count_value > 1:
            split_bodies += 1
            omitted_ranges += range_count_value - 1
        if entry != start:
            raise ValueError(f"functions[{index}] entry does not begin its contiguous body range")
        size = end - entry + 1
        contiguous_size = item.get("contiguous_size")
        if contiguous_size is not None and contiguous_size != size:
            raise ValueError(f"functions[{index}].contiguous_size does not match its range")
        if entry & 3 or size <= 0 or size & 3:
            if exclude_invalid_functions and not (entry & 3) and 0 < size < 4:
                omitted_invalid += 1
                continue
            raise ValueError(f"functions[{index}] has an unaligned or empty range")
        if entry < payload_start or end >= payload_end:
            raise ValueError(f"functions[{index}] is outside the selected payload")
        entries.append((entry, size, _normalized_name(item.get("name"), entry)))
    entries.sort()
    for previous, current in zip(entries, entries[1:]):
        if current[0] < previous[0] + previous[1]:
            raise ValueError(
                f"function ranges overlap at 0x{previous[0]:08X} and 0x{current[0]:08X}"
            )
    if len({entry for entry, _, _ in entries}) != len(entries):
        raise ValueError("duplicate function address")
    seen_names: set[str] = set()
    renamed = 0
    functions: list[dict[str, Any]] = []
    for address, size, original_name in entries:
        name = original_name
        if name in seen_names:
            name = f"{name}_{address:08X}"
            renamed += 1
        seen_names.add(name)
        functions.append({"address": f"0x{address:08X}", "name": name, "size": size})
    payload = {"functions": functions, "labels": []}
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8")
    return FuncMapConversion(
        source_sha256=source_sha256,
        output_sha256=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        payload_start=f"0x{payload_start:08X}",
        payload_size=payload_size,
        function_count=len(functions),
        renamed_symbols=renamed,
        split_body_functions=split_bodies,
        omitted_body_ranges=omitted_ranges,
        omitted_invalid_functions=omitted_invalid,
    )
