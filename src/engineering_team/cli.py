import json
from pathlib import Path
from typing import Annotated

import typer

from engineering_team.config import Settings
from engineering_team.observability.evaluation import run_multimodel_acceptance

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
    project: Annotated[Path | None, typer.Option(help="Target project; defaults to the bundled sample app")] = None,
) -> None:
    """Execute a complete local-first run with real configured Ollama models."""
    project_root = Path(__file__).resolve().parents[2]
    target = (project or project_root / "sample_app").resolve()
    if not target.is_dir():
        raise typer.BadParameter("project must be an existing directory", param_hint="--project")
    typer.echo(f"Target project: {target}")

    def progress(role, iteration):
        suffix = f"[cycle {iteration}] " if iteration else ""
        typer.echo(f"{suffix}{role}...")

    evidence = run_multimodel_acceptance(
        Settings(), requirement=requirement.strip(), report_path=report_path,
        project_target=target, progress=progress,
    )
    typer.echo(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    app()
