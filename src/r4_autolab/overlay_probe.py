from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from .analysis.iso9660 import Mode2Iso9660, cue_bin_path
from .emulator.pcsx_redux import PCSXLaunchOptions, PCSXReduxAdapter
from .emulator.transport import TcpJsonlTransport
from .models import LaunchConfig
from .state_capture import CaptureAssets, sha256_file


def find_fingerprint(data: bytes, fingerprint: bytes, max_matches: int = 16) -> list[int]:
    if not fingerprint:
        raise ValueError("fingerprint cannot be empty")
    matches: list[int] = []
    position = 0
    while len(matches) < max_matches:
        found = data.find(fingerprint, position)
        if found < 0:
            break
        matches.append(found)
        position = found + 1
    return matches


def probe_runtime_overlay(
    root: Path,
    executable: Path,
    lua_bootstrap: Path,
    state: Path,
    assets: CaptureAssets,
    address: int,
    *,
    size: int = 64,
    extract_length: int | None = None,
    timeout_seconds: float = 60.0,
) -> tuple[Path, dict[str, Any]]:
    if address < 0x80010000 or address > 0x801FFFFF - size + 1:
        raise ValueError("overlay probe must remain inside PS1 main RAM")
    if address % 4:
        raise ValueError("overlay probe address must be 4-byte aligned")
    if size < 32 or size > 256:
        raise ValueError("overlay fingerprint size must be between 32 and 256 bytes")
    if extract_length is not None and (extract_length < size or extract_length > 1024 * 1024):
        raise ValueError("overlay extraction length must be between fingerprint size and 1 MiB")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = root / "runs" / "overlay-probe" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    transport = TcpJsonlTransport()
    adapter = PCSXReduxAdapter(
        PCSXLaunchOptions(
            executable=executable,
            lua_bootstrap=lua_bootstrap,
            run=True,
            stdout=True,
            lua_stdout=True,
            interpreter=True,
            debugger=True,
            testmode=True,
            portable_directory=run_dir / "portable",
            bios=assets.bios,
            iso=assets.cue,
        ),
        transport,
    )
    fingerprint = b""
    failures: list[str] = []
    try:
        adapter.launch(LaunchConfig("overlay-probe", run_dir, timeout_seconds))
        adapter.connect()
        adapter.handshake()
        adapter.pause()
        adapter.load_state(state)
        fingerprint = adapter.read_memory(address, size)
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        try:
            adapter.shutdown()
        except Exception as error:
            failures.append(f"shutdown: {type(error).__name__}: {error}")

    files: list[dict[str, Any]] = []
    if fingerprint:
        image = Mode2Iso9660(cue_bin_path(assets.cue))
        for disc_path in ("R4.BIN", "FILE.DAT"):
            data = image.read_file(disc_path)
            matches = find_fingerprint(data, fingerprint)
            extracted: list[dict[str, Any]] = []
            if extract_length is not None:
                extraction_directory = root / "private" / "extracted" / "overlays"
                extraction_directory.mkdir(parents=True, exist_ok=True)
                for offset in matches:
                    if offset + extract_length > len(data):
                        continue
                    output = extraction_directory / f"{disc_path.lower().replace('.', '-')}-{offset:08x}.bin"
                    region = data[offset:offset + extract_length]
                    output.write_bytes(region)
                    extracted.append(
                        {
                            "offset": f"0x{offset:X}",
                            "length": len(region),
                            "sha256": hashlib.sha256(region).hexdigest(),
                            "path": str(output.resolve()),
                        }
                    )
            files.append(
                {
                    "disc_path": disc_path,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "exact_match_offsets": [f"0x{offset:X}" for offset in matches],
                    "extracted_regions": extracted,
                }
            )
    exact_matches = sum(len(item["exact_match_offsets"]) for item in files)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if exact_matches > 0 and not failures else ("UNKNOWN" if not failures else "FAIL"),
        "runtime_address": f"0x{address:08X}",
        "fingerprint_size": size,
        "fingerprint_sha256": hashlib.sha256(fingerprint).hexdigest() if fingerprint else None,
        "state_sha256": sha256_file(state),
        "files": files,
        "exact_matches": exact_matches,
        "failures": failures,
        "limitations": [
            "Only a bounded runtime code fingerprint was read; no broad RAM dump was made.",
            "Only R4.BIN and FILE.DAT were searched; the large streaming movie file was excluded.",
            "No exact match does not rule out compression, relocation, or generated code.",
        ],
    }
    report_path = run_dir / "overlay-probe.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path, report
