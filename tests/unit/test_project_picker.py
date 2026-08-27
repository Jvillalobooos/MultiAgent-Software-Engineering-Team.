from __future__ import annotations

from pathlib import Path
from typing import Protocol

from fastapi import FastAPI
from fastapi.testclient import TestClient

from engineering_team.project_api import create_project_router
from engineering_team.project_picker import WindowsFolderPicker


class StaticPicker:
    def __init__(self, selected: Path | None) -> None:
        self.selected = selected

    def pick(self) -> Path | None:
        return self.selected


def _loopback_client(app: FastAPI) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 50000))


def test_picker_returns_canonical_selected_directory(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(tmp_path / ".")))

    response = _loopback_client(app).post("/api/projects/pick")

    assert response.json() == {
        "status": "selected",
        "project": {"path": str(tmp_path.resolve()), "name": tmp_path.name},
    }


def test_picker_cancel_is_not_an_error() -> None:
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(None)))

    response = _loopback_client(app).post("/api/projects/pick")

    assert response.status_code == 200
    assert response.json() == {"status": "cancelled", "project": None}


def test_picker_rejects_non_loopback_clients(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(tmp_path)))

    response = TestClient(app, client=("192.0.2.1", 50000)).post("/api/projects/pick")

    assert response.status_code == 403
    assert response.json() == {
        "detail": {"code": "LOCAL_ONLY", "message": "Folder selection is local-only"}
    }


def test_picker_rejects_a_selected_path_that_is_not_a_directory(tmp_path: Path) -> None:
    selected_file = tmp_path / "not-a-project.txt"
    selected_file.write_text("not a directory")
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(selected_file)))

    response = _loopback_client(app).post("/api/projects/pick")

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "INVALID_PROJECT", "message": "Selected path is not a directory"}
    }


class MonkeyPatch(Protocol):
    def setattr(self, target: str, value: object) -> None: ...


def test_windows_picker_rejects_non_windows_without_initializing_tk(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("engineering_team.project_picker.sys.platform", "linux")

    try:
        WindowsFolderPicker().pick()
    except RuntimeError as exc:
        assert str(exc) == "native folder selection requires Windows"
    else:
        raise AssertionError("WindowsFolderPicker should reject non-Windows platforms")
