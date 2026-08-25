from pathlib import Path


def resolve_inside(root: str | Path, relative: str | Path) -> Path:
    root_path = Path(root).resolve()
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("path must remain inside workspace")
    target = (root_path / relative_path).resolve()
    if target != root_path and root_path not in target.parents:
        raise ValueError("resolved path is outside workspace")
    return target
