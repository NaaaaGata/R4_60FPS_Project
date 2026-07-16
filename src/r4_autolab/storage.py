from __future__ import annotations

from contextlib import AbstractContextManager
import json
from pathlib import Path
import sqlite3
from typing import Any

from .models import ExperimentProposal, ExperimentState, RunSummary


class ExperimentStore(AbstractContextManager["ExperimentStore"]):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                scenario TEXT NOT NULL,
                hypothesis TEXT NOT NULL,
                target_serial TEXT NOT NULL,
                target_sha256 TEXT NOT NULL,
                proposal_json TEXT NOT NULL,
                state TEXT NOT NULL,
                summary_json TEXT,
                run_dir TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS transitions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL REFERENCES experiments(id),
                from_state TEXT,
                to_state TEXT NOT NULL,
                detail TEXT,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS comparisons (
                baseline_id TEXT NOT NULL,
                experiment_id TEXT NOT NULL,
                comparison_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (baseline_id, experiment_id)
            );
            """
        )
        self.connection.commit()

    def create(self, proposal: ExperimentProposal, kind: str, scenario: str, run_dir: Path) -> None:
        proposal_json = json.dumps(proposal.to_dict(), sort_keys=True)
        self.connection.execute(
            """INSERT INTO experiments
            (id, kind, scenario, hypothesis, target_serial, target_sha256,
             proposal_json, state, run_dir)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                proposal.id,
                kind,
                scenario,
                proposal.hypothesis,
                proposal.target_version.serial,
                proposal.target_version.executable_sha256,
                proposal_json,
                ExperimentState.CREATED.value,
                str(run_dir),
            ),
        )
        self.connection.execute(
            "INSERT INTO transitions (experiment_id, from_state, to_state) VALUES (?, ?, ?)",
            (proposal.id, None, ExperimentState.CREATED.value),
        )
        self.connection.commit()

    def transition(
        self,
        experiment_id: str,
        old: ExperimentState,
        new: ExperimentState,
        detail: str | None = None,
    ) -> None:
        self.connection.execute(
            "UPDATE experiments SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new.value, experiment_id),
        )
        self.connection.execute(
            "INSERT INTO transitions (experiment_id, from_state, to_state, detail) VALUES (?, ?, ?, ?)",
            (experiment_id, old.value, new.value, detail),
        )
        self.connection.commit()

    def complete(self, experiment_id: str, summary: RunSummary) -> None:
        self.connection.execute(
            "UPDATE experiments SET summary_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(summary.to_dict(), sort_keys=True), experiment_id),
        )
        self.connection.commit()

    def set_error(self, experiment_id: str, error: str) -> None:
        self.connection.execute(
            "UPDATE experiments SET error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (error, experiment_id),
        )
        self.connection.commit()

    def get(self, experiment_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown experiment: {experiment_id}")
        value = dict(row)
        if value["summary_json"]:
            value["summary"] = json.loads(value["summary_json"])
        value["proposal"] = json.loads(value["proposal_json"])
        return value

    def list_records(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM experiments ORDER BY created_at, id"
        )]

    def save_comparison(self, baseline_id: str, experiment_id: str, value: dict[str, Any]) -> None:
        self.connection.execute(
            """INSERT OR REPLACE INTO comparisons
            (baseline_id, experiment_id, comparison_json) VALUES (?, ?, ?)""",
            (baseline_id, experiment_id, json.dumps(value, sort_keys=True)),
        )
        self.connection.commit()

    def transitions(self, experiment_id: str) -> list[str]:
        rows = self.connection.execute(
            "SELECT to_state FROM transitions WHERE experiment_id = ? ORDER BY sequence",
            (experiment_id,),
        )
        return [str(row[0]) for row in rows]

    def close(self) -> None:
        self.connection.close()

    def __exit__(self, *args: object) -> None:
        self.close()
