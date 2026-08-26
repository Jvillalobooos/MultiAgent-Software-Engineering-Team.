from pathlib import Path

from typer.testing import CliRunner

from engineering_team import cli


def test_cli_accepts_requirement_and_reports_run_evidence(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_run(settings, *, requirement, report_path, project_target, progress):
        captured.update(requirement=requirement, report_path=report_path, project_target=project_target)
        return {"run_id": "run-1", "trace_id": "trace-1", "final_status": "APPROVED"}

    monkeypatch.setattr(cli, "run_multimodel_acceptance", fake_run)
    result = CliRunner().invoke(
        cli.app, ["run", "password recovery", "--report-path", str(tmp_path / "run.json")]
    )

    assert result.exit_code == 0
    assert '"final_status": "APPROVED"' in result.stdout
    assert captured["requirement"] == "password recovery"
    assert captured["project_target"] == (Path(cli.__file__).resolve().parents[2] / "sample_app")


def test_cli_uses_explicit_project_target(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_run(settings, *, requirement, report_path, project_target, progress):
        captured.update(project_target=project_target, requirement=requirement)
        return {"run_id": "run-1", "trace_id": "trace-1", "final_status": "APPROVED"}

    monkeypatch.setattr(cli, "run_multimodel_acceptance", fake_run)
    result = CliRunner().invoke(
        cli.app, ["run", "password recovery", "--project", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert captured["project_target"] == tmp_path.resolve()


def test_cli_prints_resolved_target_before_running(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "run_multimodel_acceptance", lambda *args, **kwargs: {"final_status": "APPROVED"})

    result = CliRunner().invoke(cli.app, ["run", "safe change", "--project", str(tmp_path)])

    assert result.exit_code == 0
    assert f"Target project: {tmp_path.resolve()}" in result.stdout
