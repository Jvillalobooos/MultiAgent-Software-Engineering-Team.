from pathlib import Path

from .isolation import create_run_copy


class RunWorkspaceFactory:
    def __init__(self, root: str | Path, source: str | Path) -> None:
        self.root = Path(root)
        self.source = Path(source)

    def create(self, run_id: str) -> Path:
        return create_run_copy(run_id, self.source, self.root)
