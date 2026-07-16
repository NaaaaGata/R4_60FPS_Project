from __future__ import annotations

from typing import Any


def render_run_report(record: dict[str, Any], transitions: list[str]) -> str:
    summary = record.get("summary") or {}
    lines = [
        f"# R4 AutoLab run: {record['id']}",
        "",
        f"- Kind: `{record['kind']}`",
        f"- State: `{record['state']}`",
        f"- Scenario: `{record['scenario']}`",
        f"- Hypothesis: {record['hypothesis']}",
        f"- Target serial: `{record['target_serial']}`",
        f"- Target executable SHA-256: `{record['target_sha256'] or 'unverified'}`",
        "",
        "## State transitions",
        "",
        " → ".join(f"`{state}`" for state in transitions),
        "",
        "## Summary",
        "",
    ]
    if summary:
        lines.extend(f"- {key}: `{value}`" for key, value in sorted(summary.items()))
    else:
        lines.append("No summary is available.")
    if record.get("error"):
        lines.extend(["", "## Error", "", str(record["error"])])
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This report records measurements only. It does not by itself confirm real 60 fps behavior.",
            "",
        ]
    )
    return "\n".join(lines)

