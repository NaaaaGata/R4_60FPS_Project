import json
from pathlib import Path
from typing import Any


def _assert_all_properties_required(value: dict[str, Any]) -> None:
    properties = value.get("properties")
    if isinstance(properties, dict):
        assert set(value.get("required", [])) == set(properties)
        for child in properties.values():
            if isinstance(child, dict):
                _assert_all_properties_required(child)
    items = value.get("items")
    if isinstance(items, dict):
        _assert_all_properties_required(items)


def test_codex_output_schema_requires_every_declared_property() -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "schemas/experiment_proposal.schema.json").read_text()
    )
    _assert_all_properties_required(schema)
