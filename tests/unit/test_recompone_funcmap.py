from __future__ import annotations

import json
from pathlib import Path

import pytest

from r4_autolab.recompone.funcmap import convert_ghidra_export


def _export() -> dict[str, object]:
    return {
        "input_sha256": "a" * 64,
        "language_id": "MIPS:LE:32:default",
        "memory_blocks": [
            {"name": "R4_PAYLOAD", "start": "0x80010000", "end": "0x80010FFF", "size": 0x1000}
        ],
        "functions": [
            {
                "name": "same.name",
                "entry": "0x80010000",
                "start": "0x80010000",
                "end": "0x8001003F",
                "body_range_count": 2,
                "contiguous_start": "0x80010000",
                "contiguous_end": "0x8001001F",
                "contiguous_size": 0x20,
            },
            {
                "name": "same-name",
                "entry": "0x80010020",
                "start": "0x80010020",
                "end": "0x8001002F",
                "body_range_count": 1,
                "contiguous_start": "0x80010020",
                "contiguous_end": "0x8001002F",
                "contiguous_size": 0x10,
            },
        ],
    }


def test_conversion_is_deterministic_and_classifies_split_bodies(tmp_path: Path) -> None:
    source = tmp_path / "export.json"
    source.write_text(json.dumps(_export()), encoding="utf-8")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    result = convert_ghidra_export(source, first, block_name="R4_PAYLOAD")
    again = convert_ghidra_export(source, second, block_name="R4_PAYLOAD")
    assert first.read_bytes() == second.read_bytes()
    assert result.output_sha256 == again.output_sha256
    assert result.function_count == 2
    assert result.renamed_symbols == 1
    assert result.split_body_functions == 1
    assert result.omitted_body_ranges == 1
    assert result.omitted_invalid_functions == 0
    value = json.loads(first.read_text(encoding="utf-8"))
    assert value["functions"] == [
        {"address": "0x80010000", "name": "same_name", "size": 32},
        {"address": "0x80010020", "name": "same_name_80010020", "size": 16},
    ]
    assert value["labels"] == []


def test_rejects_overlapping_contiguous_ranges(tmp_path: Path) -> None:
    value = _export()
    value["functions"][1]["entry"] = "0x80010010"  # type: ignore[index]
    value["functions"][1]["contiguous_start"] = "0x80010010"  # type: ignore[index]
    value["functions"][1]["contiguous_size"] = 0x20  # type: ignore[index]
    source = tmp_path / "export.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        convert_ghidra_export(source, tmp_path / "map.json")


def test_rejects_old_noncontiguous_entry_without_explicit_range(tmp_path: Path) -> None:
    value = _export()
    item = value["functions"][0]  # type: ignore[index]
    for field in ("body_range_count", "contiguous_start", "contiguous_end", "contiguous_size"):
        item.pop(field)  # type: ignore[union-attr]
    item["start"] = "0x8000FFF0"  # type: ignore[index]
    source = tmp_path / "export.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="entry does not begin"):
        convert_ghidra_export(source, tmp_path / "map.json")


def test_explicitly_classifies_instruction_width_invalid_function(tmp_path: Path) -> None:
    value = _export()
    value["functions"].append(  # type: ignore[union-attr]
        {
            "name": "phantom",
            "entry": "0x80010040",
            "start": "0x80010040",
            "end": "0x80010040",
            "body_range_count": 1,
            "contiguous_start": "0x80010040",
            "contiguous_end": "0x80010040",
            "contiguous_size": 1,
        }
    )
    source = tmp_path / "export.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="unaligned or empty"):
        convert_ghidra_export(source, tmp_path / "strict.json")
    result = convert_ghidra_export(
        source,
        tmp_path / "classified.json",
        exclude_invalid_functions=True,
    )
    assert result.function_count == 2
    assert result.omitted_invalid_functions == 1


def test_rejects_inconsistent_contiguous_size(tmp_path: Path) -> None:
    value = _export()
    value["functions"][0]["contiguous_size"] = 4  # type: ignore[index]
    source = tmp_path / "export.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="contiguous_size"):
        convert_ghidra_export(source, tmp_path / "map.json")
