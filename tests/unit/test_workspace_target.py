from pathlib import Path

from engineering_team.workspace.isolation import create_run_copy


def test_run_copy_keeps_original_target_byte_for_byte(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "app.py"
    original = b"def change_email(current_password, email):\n    return email\n"
    source.write_bytes(original)

    workspace = create_run_copy("run-1", target, tmp_path / "runs")
    (workspace / "app.py").write_text("changed\n", encoding="utf-8")

    assert source.read_bytes() == original
    assert (workspace / "app.py").read_text(encoding="utf-8") == "changed\n"


def test_run_copy_ignores_local_environment_and_previous_runs(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / ".venv").mkdir()
    (target / ".venv" / "ignored").write_text("x", encoding="utf-8")
    (target / "workspace" / "runs").mkdir(parents=True)
    (target / "workspace" / "runs" / "old.txt").write_text("x", encoding="utf-8")
    (target / "package.py").write_text("x", encoding="utf-8")

    workspace = create_run_copy("run-2", target, tmp_path / "runs")

    assert (workspace / "package.py").exists()
    assert not (workspace / ".venv").exists()
    assert not (workspace / "workspace" / "runs").exists()
