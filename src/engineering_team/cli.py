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
) -> None:
    """Execute a complete local-first run with real configured Ollama models."""
    evidence = run_multimodel_acceptance(
        Settings(), requirement=requirement.strip(), report_path=report_path
    )
    typer.echo(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    app()
