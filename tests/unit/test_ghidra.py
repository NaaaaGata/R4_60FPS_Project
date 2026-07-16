from pathlib import Path

from r4_autolab.ghidra.exports import load_static_export
from r4_autolab.ghidra.runner import FakeGhidraRunner, GhidraRunConfig, build_headless_args, cache_key


def test_headless_args_are_array_based_and_include_postscript(tmp_path: Path) -> None:
    config = GhidraRunConfig(
        Path("analyzeHeadless"),
        tmp_path / "input.exe",
        tmp_path / "export.json",
        tmp_path / "project",
        tmp_path / "scripts",
        (0x80010000,),
        "MIPS:LE:32:default",
        60,
    )
    arguments = build_headless_args(config)
    assert arguments[:3] == ["analyzeHeadless", str(tmp_path / "project"), "r4-autolab-temp"]
    assert "-import" in arguments
    assert arguments[arguments.index("-postScript") + 1] == "R4Export.java"
    assert "0x80010000" in arguments
    assert "-deleteProject" in arguments


def test_fake_export_and_cache_key_are_deterministic(tmp_path: Path) -> None:
    input_file = tmp_path / "input.exe"
    input_file.write_bytes(b"PS-X EXE" + b"\0" * 64)
    script = tmp_path / "R4Export.java"
    script.write_text("script", encoding="utf-8")
    first = cache_key(input_file, script, (0x80010000,), None)
    second = cache_key(input_file, script, (0x80010000,), None)
    assert first == second
    config = GhidraRunConfig(
        Path("fake"), input_file, tmp_path / "export.json", tmp_path / "project", tmp_path, (0x80010000,)
    )
    FakeGhidraRunner().run(config, tmp_path / "ghidra.log")
    summary = load_static_export(config.output_file)
    assert summary.requested_addresses == ("0x80010000",)
    assert summary.function_count == 0


def test_binary_loader_arguments_preserve_psx_payload_mapping(tmp_path: Path) -> None:
    config = GhidraRunConfig(
        analyze_headless=Path("analyzeHeadless"),
        input_file=tmp_path / "SLPS_018.00",
        output_file=tmp_path / "export.json",
        project_directory=tmp_path / "project",
        script_directory=tmp_path / "scripts",
        addresses=(0x80050194,),
        processor="MIPS:LE:32:default",
        timeout_seconds=60,
        loader="BinaryLoader",
        loader_base_address=0x80010000,
        loader_file_offset=0x800,
        loader_length=638976,
        loader_block_name="R4_PAYLOAD",
        entry_point=0x8007D4B4,
        global_pointer=0x800ABBE8,
    )
    arguments = build_headless_args(config)
    expected_pairs = {
        "-loader": "BinaryLoader",
        "-loader-baseAddr": "0x80010000",
        "-loader-fileOffset": "0x800",
        "-loader-length": "0x9C000",
        "-loader-blockName": "R4_PAYLOAD",
        "-processor": "MIPS:LE:32:default",
        "-preScript": "R4Prepare.java",
    }
    for flag, value in expected_pairs.items():
        assert arguments[arguments.index(flag) + 1] == value
