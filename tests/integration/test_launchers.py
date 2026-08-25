from pathlib import Path


def test_launchers_forward_caller_directory_as_project_target() -> None:
    root = Path(__file__).parents[2]
    powershell = (root / "run.ps1").read_text(encoding="utf-8")
    shell = (root / "run.sh").read_text(encoding="utf-8")

    assert "--project $targetProject" in powershell
    assert '--project "$CALLER_PROJECT"' in shell
    assert 'LauncherArguments[0] -eq "--project"' in powershell
    assert '[ "$1" = "--project" ]' in shell
