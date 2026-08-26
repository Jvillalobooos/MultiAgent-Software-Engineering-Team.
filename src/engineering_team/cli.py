import json
from pathlib import Path
from typing import Annotated

import typer

from engineering_team.apply_run import run_on_project
from engineering_team.config import Settings
from engineering_team.observability.evaluation import run_multimodel_acceptance
from engineering_team.reset_project import reset_project

app = typer.Typer(help="Governed autonomous software-engineering workflow")


@app.callback()
def main() -> None:
    """Use a subcommand to run or evaluate the local team."""


@app.command()
def run(
    requirement: Annotated[str, typer.Argument(min=1)],
    report_path: Annotated[Path, typer.Option(help="Sanitized evidence output")] = Path(
        "evaluation/reports/cli-run.json"
    ),
) -> None:
    """Execute a complete local-first run with real configured Ollama models."""
    evidence = run_multimodel_acceptance(
        Settings(), requirement=requirement.strip(), report_path=report_path
    )
    typer.echo(json.dumps(evidence, ensure_ascii=False))


@app.command("run-project")
def run_project(
    project_path: Annotated[Path, typer.Argument(help="Real project directory to run against")],
    specification: Annotated[str, typer.Option("--spec", help="Functional specification")],
    test_specification: Annotated[
        str | None, typer.Option("--test-spec", help="Test expectations")
    ] = None,
    authorize_writes: Annotated[
        bool,
        typer.Option(
            "--authorize-writes/--dry-run",
            help="Explicitly authorize writing changes to project_path (destructive-change guardrail)",
        ),
    ] = False,
    report_path: Annotated[Path, typer.Option(help="Sanitized evidence output")] = Path(
        "evaluation/reports/apply-run.json"
    ),
) -> None:
    """Run Product->Architecture->Developer->Security->Testing->Reviewer against a
    real project and, when --authorize-writes is passed, apply the changes for real."""
    evidence = run_on_project(
        Settings(),
        project_path=project_path,
        specification=specification,
        test_specification=test_specification,
        authorize_writes=authorize_writes,
        report_path=report_path,
    )
    typer.echo(json.dumps(evidence, ensure_ascii=False))


@app.command("reset-project")
def reset_project_command(
    project_path: Annotated[Path, typer.Argument(help="Demo project git repo to reset")],
) -> None:
    """Hard-reset a demo project (e.g. demo-projects/calculadora-qa-demo) back to
    its initial commit, discarding any changes run-project applied to it."""
    evidence = reset_project(project_path)
    typer.echo(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    app()
