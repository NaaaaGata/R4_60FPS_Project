from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from r4_autolab.recompone.config import load_recompone_config
from r4_autolab.recompone.runner import RecompOneRunner, git_ignores_path, run_bounded_process
from r4_autolab.recompone.tool import PINNED_RECOMPONE_COMMIT, RecompOneTool


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    config_dir = tmp_path / "private/recompone/config"
    maps = tmp_path / "private/recompone/function-maps"
    config_dir.mkdir(parents=True)
    maps.mkdir(parents=True)
    (maps / "main.json").write_text("{}\n", encoding="utf-8")
    cue = tmp_path / "game.cue"
    cue.write_text('FILE "game.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")
    (tmp_path / "game.bin").write_bytes(b"original")
    value = {
        "game": {"id": "TEST", "name": "Synthetic", "output": "../generated/test"},
        "cue": "../../../game.cue",
        "funcMap": "../function-maps/main.json",
        "linearSweep": False,
        "debug": False,
        "overlays": [],
        "stubs": [],
        "ignored": [],
        "patches": [],
    }
    config = config_dir / "test.json"
    config.write_text(json.dumps(value), encoding="utf-8")
    return config, tmp_path / "private/recompone/generated/test"


def _tool(script: Path) -> RecompOneTool:
    return RecompOneTool(
        path=script,
        launcher=(sys.executable, str(script)),
        source_root=None,
        commit=PINNED_RECOMPONE_COMMIT,
        source_dirty=False,
        dotnet_path=Path(sys.executable),
        dotnet_version="10.0.201",
        license_name="MIT",
    )


def test_fake_generation_records_hashes_and_private_outputs(tmp_path: Path) -> None:
    config_path, output = _fixture(tmp_path)
    script = tmp_path / "fake_recompone.py"
    script.write_text(
        """import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
v = json.loads(p.read_text())
out = (p.parent / v['game']['output']).resolve()
out.mkdir(parents=True, exist_ok=True)
(out / 'Entry.cs').write_text('// synthetic')
print('[RecompOne] Recompilation finished.')
""",
        encoding="utf-8",
    )
    config = load_recompone_config(config_path, tmp_path)
    report = RecompOneRunner(_tool(script), timeout_seconds=5).generate(config, tmp_path / "run")
    assert report["status"] == "PASS"
    assert report["source_hashes_unchanged"] is True
    assert report["unknown_instructions"] == 0
    assert report["process"]["command"][-1] == "<private-config>"
    assert str(tmp_path) not in json.dumps(report)
    assert report["runtime_started"] is False
    assert report["r4_memory_writes"] == 0
    assert (output / "Entry.cs").is_file()


def test_generation_fails_on_unknown_instruction_or_missing_output(tmp_path: Path) -> None:
    config_path, _ = _fixture(tmp_path)
    script = tmp_path / "fake_recompone.py"
    script.write_text("print('[Unknown] synthetic instruction')\n", encoding="utf-8")
    config = load_recompone_config(config_path, tmp_path)
    report = RecompOneRunner(_tool(script), timeout_seconds=5).generate(config, tmp_path / "run")
    assert report["status"] == "FAIL"
    assert report["unknown_instructions"] == 1
    assert report["generated_files"] == []


def test_generation_fails_on_unmapped_dispatch_candidate(tmp_path: Path) -> None:
    config_path, _ = _fixture(tmp_path)
    script = tmp_path / "fake_recompone.py"
    script.write_text(
        """import json, pathlib, sys
config = pathlib.Path(sys.argv[1])
value = json.loads(config.read_text())
output = (config.parent / value['game']['output']).resolve()
output.mkdir(parents=True, exist_ok=True)
(output / 'Entry.cs').write_text('Dispatcher.Call(c, m, 0x80012340u);')
""",
        encoding="utf-8",
    )
    config = load_recompone_config(config_path, tmp_path)
    report = RecompOneRunner(_tool(script), timeout_seconds=5).generate(config, tmp_path / "run")
    assert report["status"] == "FAIL"
    assert report["unmapped_call_log_events"] == 0
    assert report["unmapped_call_candidates"] == 1
    assert report["unmapped_call_candidate_addresses"] == ["0x80012340"]


def test_generation_fails_on_nonzero_exit_and_asset_mutation(tmp_path: Path) -> None:
    config_path, _ = _fixture(tmp_path)
    script = tmp_path / "fake_recompone.py"
    script.write_text(
        """import json, pathlib, sys
config = pathlib.Path(sys.argv[1])
value = json.loads(config.read_text())
output = (config.parent / value['game']['output']).resolve()
output.mkdir(parents=True, exist_ok=True)
(output / 'Entry.cs').write_text('// partial')
config.parents[3].joinpath('game.bin').write_bytes(b'mutated')
raise SystemExit(7)
""",
        encoding="utf-8",
    )
    config = load_recompone_config(config_path, tmp_path)
    report = RecompOneRunner(_tool(script), timeout_seconds=5).generate(config, tmp_path / "run")
    assert report["status"] == "FAIL"
    assert report["process"]["exit_code"] == 7
    assert report["source_hashes_unchanged"] is False
    assert len(report["generated_files"]) == 1


def test_bounded_process_kills_residual_child(tmp_path: Path) -> None:
    script = tmp_path / "child.py"
    script.write_text(
        "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n",
        encoding="utf-8",
    )
    result = run_bounded_process(
        [sys.executable, str(script)],
        cwd=tmp_path,
        log_path=tmp_path / "child.log",
        timeout_seconds=5,
        max_log_bytes=1024,
    )
    assert result.forced_cleanup
    assert result.residual_processes is False


def test_repository_private_generated_path_is_git_ignored() -> None:
    root = Path(__file__).resolve().parents[2]
    assert git_ignores_path(root, root / "private/recompone/generated/probe.cs") is True


def test_bounded_process_enforces_timeout_and_log_cap(tmp_path: Path) -> None:
    sleeper = tmp_path / "sleep.py"
    sleeper.write_text("import time; print('started', flush=True); time.sleep(30)\n", encoding="utf-8")
    timed = run_bounded_process(
        [sys.executable, str(sleeper)],
        cwd=tmp_path,
        log_path=tmp_path / "timeout.log",
        timeout_seconds=0.1,
        max_log_bytes=1024,
    )
    assert timed.timed_out
    assert timed.exit_code != 0

    noisy = tmp_path / "noisy.py"
    noisy.write_text("import os; os.write(1, b'x' * 4096)\n", encoding="utf-8")
    capped = run_bounded_process(
        [sys.executable, str(noisy)],
        cwd=tmp_path,
        log_path=tmp_path / "capped.log",
        timeout_seconds=5,
        max_log_bytes=128,
    )
    assert capped.log_limit_exceeded
    assert capped.log_bytes == 128
    assert os.path.getsize(tmp_path / "capped.log") == 128
