from pathlib import Path
import shutil

from r4_autolab.cli import main


def test_cli_fake_baseline_candidate_compare_and_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "config").mkdir()
    config = (root / "config/project.example.toml").read_text(encoding="utf-8")
    (tmp_path / "config/project.toml").write_text(config, encoding="utf-8")
    shutil.copyfile(root / "config/fake_candidate.example.json", tmp_path / "candidate.json")
    config_path = tmp_path / "config/project.toml"
    assert main(["--config", str(config_path), "baseline", "--scenario", "fake", "--id", "base"]) == 0
    assert main(["--config", str(config_path), "experiment", "--proposal", str(tmp_path / "candidate.json")]) == 0
    assert main(["--config", str(config_path), "compare", "base", "candidate-fake-render-60hz"]) == 0
    report = tmp_path / "report.md"
    assert main(["--config", str(config_path), "report", "candidate-fake-render-60hz", "--output", str(report)]) == 0
    assert "State transitions" in report.read_text(encoding="utf-8")

