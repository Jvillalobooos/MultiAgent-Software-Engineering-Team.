from typer.testing import CliRunner

from engineering_team import cli


def test_cli_accepts_requirement_and_reports_run_evidence(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_run(settings, *, requirement, report_path):
        captured.update(requirement=requirement, report_path=report_path)
        return {"run_id": "run-1", "trace_id": "trace-1", "final_status": "APPROVED"}

    monkeypatch.setattr(cli, "run_multimodel_acceptance", fake_run)
    result = CliRunner().invoke(
        cli.app, ["run", "password recovery", "--report-path", str(tmp_path / "run.json")]
    )

    assert result.exit_code == 0
    assert '"final_status": "APPROVED"' in result.stdout
    assert captured["requirement"] == "password recovery"
