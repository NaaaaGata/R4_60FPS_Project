from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StaticExportSummary:
    input_sha256: str
    language_id: str
    image_base: str
    function_count: int
    xref_count: int
    requested_addresses: tuple[str, ...]


def load_static_export(path: Path) -> StaticExportSummary:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("static export must be a JSON object")
    required = {"input_sha256", "language_id", "image_base", "functions", "xrefs", "requested_addresses"}
    missing = required - value.keys()
    if missing:
        raise ValueError("static export is missing: " + ", ".join(sorted(missing)))
    functions = value["functions"]
    xrefs = value["xrefs"]
    addresses = value["requested_addresses"]
    if not isinstance(functions, list) or not isinstance(xrefs, list) or not isinstance(addresses, list):
        raise ValueError("static export collections have invalid types")
    return StaticExportSummary(
        input_sha256=str(value["input_sha256"]),
        language_id=str(value["language_id"]),
        image_base=str(value["image_base"]),
        function_count=len(functions),
        xref_count=len(xrefs),
        requested_addresses=tuple(str(item) for item in addresses),
    )

