from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class CadenceStats:
    samples: int
    elapsed_seconds: float
    unique_values: int
    changes: int
    update_hz: float
    duplicate_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_cadence(events: Iterable[dict[str, Any]], field: str) -> CadenceStats:
    values = list(events)
    if not values:
        raise ValueError("cadence analysis requires events")
    observed = [event.get(field) for event in values]
    changes = sum(left != right for left, right in zip(observed, observed[1:]))
    duplicates = max(0, len(observed) - 1 - changes)
    first_time = float(values[0].get("monotonic_timestamp", 0.0))
    last_time = float(values[-1].get("monotonic_timestamp", first_time))
    elapsed = max(0.0, last_time - first_time)
    return CadenceStats(
        samples=len(values),
        elapsed_seconds=elapsed,
        unique_values=len({repr(value) for value in observed}),
        changes=changes,
        update_hz=changes / elapsed if elapsed else 0.0,
        duplicate_ratio=duplicates / max(1, len(observed) - 1),
    )
