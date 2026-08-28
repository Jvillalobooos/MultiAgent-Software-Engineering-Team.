from __future__ import annotations

import base64
import logging
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import raises

from engineering_team import project_picker
from engineering_team.project_api import create_project_router
from engineering_team.project_picker import (
    MacOSFolderPicker,
    NativeFolderPicker,
    PickerBusyError,
    WindowsFolderPicker,
)


class StaticPicker:
    def __init__(self, selected: Path | None) -> None:
        self.selected = selected

    def pick(self) -> Path | None:
        return self.selected


class FailingPicker:
    def pick(self) -> Path | None:
        raise RuntimeError("native picker failed")


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
        "detail": {
            "code": "INVALID_PROJECT_PATH",
            "message": "Project path must be an existing directory.",
        }
    }


def test_native_picker_dispatches_to_the_macos_adapter(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "project"
    selected.mkdir()
    calls: list[str] = []

    def pick_on_macos(_picker: MacOSFolderPicker) -> Path:
        calls.append("macos")
        return selected

    monkeypatch.setattr(project_picker.sys, "platform", "darwin")
    monkeypatch.setattr(MacOSFolderPicker, "pick", pick_on_macos)

    assert NativeFolderPicker().pick() == selected
    assert calls == ["macos"]


def test_native_picker_dispatches_to_the_windows_adapter(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "project"
    selected.mkdir()
    calls: list[str] = []

    def pick_on_windows(_picker: WindowsFolderPicker) -> Path:
        calls.append("windows")
        return selected

    monkeypatch.setattr(project_picker.sys, "platform", "win32")
    monkeypatch.setattr(WindowsFolderPicker, "pick", pick_on_windows)

    assert NativeFolderPicker().pick() == selected
    assert calls == ["windows"]


def test_native_picker_rejects_an_unsupported_platform(monkeypatch) -> None:
    monkeypatch.setattr(project_picker.sys, "platform", "linux")

    with raises(RuntimeError, match="macOS or Windows"):
        NativeFolderPicker().pick()


def test_macos_picker_returns_a_unicode_directory_from_osascript(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "proyecto-caf\u00e9"
    selected.mkdir()
    captured: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, f"{selected}\n", "")

    monkeypatch.setattr(project_picker.subprocess, "run", run)

    assert MacOSFolderPicker().pick() == selected.resolve()
    assert captured["command"][:3] == ["osascript", "-l", "JavaScript"]
    assert captured["kwargs"] == {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "check": True,
        "timeout": 120,
    }


def test_macos_picker_treats_an_empty_native_result_as_cancelled(monkeypatch) -> None:
    monkeypatch.setattr(
        project_picker.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "\n", ""),
    )

    assert MacOSFolderPicker().pick() is None


def test_macos_picker_uses_jxa_property_invocation_for_zero_argument_methods(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(project_picker.subprocess, "run", run)

    assert MacOSFolderPicker().pick() is None
    script = captured["command"][-1]

    assert "panel.center;" in script
    assert "Number(panel.runModal)" in script
    assert "panel.center()" not in script
    assert "panel.runModal()" not in script


def test_macos_picker_reports_a_native_timeout(monkeypatch) -> None:
    def timeout(command: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(command, 120)

    monkeypatch.setattr(project_picker.subprocess, "run", timeout)

    with raises(RuntimeError, match="timed out"):
        MacOSFolderPicker().pick()


def test_macos_picker_logs_bounded_native_stderr_on_failure(monkeypatch, caplog) -> None:
    stderr = "x" * 1000

    def fail(command: list[str], **kwargs: object) -> None:
        raise subprocess.CalledProcessError(7, command, stderr=stderr)

    monkeypatch.setattr(project_picker.subprocess, "run", fail)
    caplog.set_level(logging.WARNING, logger="engineering_team.project_picker")

    with raises(RuntimeError, match="picker failed"):
        MacOSFolderPicker().pick()

    assert "exit 7" in caplog.text
    assert "[truncated]" in caplog.text
    assert stderr not in caplog.text


def test_windows_picker_uses_hidden_sta_powershell_and_utf8(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "proyecto-caf\u00e9"
    selected.mkdir()
    captured: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, f"{selected}\n", "")

    monkeypatch.setattr(project_picker.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(project_picker.subprocess, "run", run)

    assert WindowsFolderPicker().pick() == selected.resolve()
    assert captured["command"][:5] == [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy",
    ]
    assert "-EncodedCommand" in captured["command"]
    assert captured["kwargs"] == {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "check": True,
        "timeout": 120,
        "creationflags": 0x08000000,
    }


def test_windows_picker_uses_a_powershell_51_compatible_dialog_script(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(project_picker.subprocess, "run", run)

    assert WindowsFolderPicker().pick() is None
    command = captured["command"]
    encoded_script = command[command.index("-EncodedCommand") + 1]
    script = base64.b64decode(encoded_script).decode("utf-16-le")

    assert "private readonly IntPtr _handle = GetForegroundWindow();" in script
    assert "public IntPtr Handle { get { return _handle; } }" in script
    assert "=>" not in script
    assert "$dialog.PSObject.Properties.Name -contains 'AutoUpgradeEnabled'" in script
    assert "[System.Windows.Forms.FolderBrowserDialog]::new()" not in script
    assert "[System.Text.UTF8Encoding]::new($false)" not in script


def test_native_picker_rejects_a_second_request_instead_of_queueing(monkeypatch) -> None:
    picker = MacOSFolderPicker()
    assert picker._lock.acquire(blocking=False)
    try:
        with raises(PickerBusyError, match="already open"):
            picker.pick()
    finally:
        picker._lock.release()


def test_manual_selection_returns_a_canonical_unicode_project(tmp_path: Path) -> None:
    selected = tmp_path / "proyecto-caf\u00e9"
    selected.mkdir()
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(None)))

    response = _loopback_client(app).post("/api/projects/select", json={"path": str(selected)})

    assert response.status_code == 200
    assert response.json() == {
        "status": "selected",
        "project": {"path": str(selected.resolve()), "name": "proyecto-caf\u00e9"},
    }


def test_manual_selection_rejects_a_relative_path(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(tmp_path)))

    response = _loopback_client(app).post("/api/projects/select", json={"path": "relative/project"})

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "PROJECT_PATH_MUST_BE_ABSOLUTE",
            "message": "Project path must be absolute.",
        }
    }


def test_manual_selection_rejects_a_missing_or_file_path(tmp_path: Path) -> None:
    selected_file = tmp_path / "not-a-directory.txt"
    selected_file.write_text("not a directory")
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(tmp_path)))

    for invalid in (tmp_path / "missing", selected_file):
        response = _loopback_client(app).post("/api/projects/select", json={"path": str(invalid)})

        assert response.status_code == 422
        assert response.json() == {
            "detail": {
                "code": "INVALID_PROJECT_PATH",
                "message": "Project path must be an existing directory.",
            }
        }


def test_manual_selection_rejects_an_invalid_filesystem_path(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(tmp_path)))

    response = _loopback_client(app).post("/api/projects/select", json={"path": "/\u0000"})

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_PROJECT_PATH",
            "message": "Project path must be an existing directory.",
        }
    }


def test_manual_selection_rejects_non_loopback_clients(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(tmp_path)))

    response = TestClient(app, client=("192.0.2.1", 50000)).post(
        "/api/projects/select", json={"path": str(tmp_path)}
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": {"code": "LOCAL_ONLY", "message": "Folder selection is local-only"}
    }


def test_picker_failure_is_reported_as_a_recoverable_api_error() -> None:
    app = FastAPI()
    app.include_router(create_project_router(FailingPicker()))

    response = _loopback_client(app).post("/api/projects/pick")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "PICKER_UNAVAILABLE",
            "message": "native picker failed",
            "recoverable": True,
        }
    }
