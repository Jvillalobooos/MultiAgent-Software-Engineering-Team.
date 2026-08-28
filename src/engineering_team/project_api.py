"""Local-only HTTP transport for selecting a project directory."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from engineering_team.project_picker import FolderPicker, NativeFolderPicker, PickerBusyError


class ProjectRef(BaseModel):
    path: str
    name: str


class ProjectPickResponse(BaseModel):
    status: Literal["selected", "cancelled"]
    project: ProjectRef | None


class ProjectSelectRequest(BaseModel):
    path: str = Field(min_length=1)


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    return ipaddress.ip_address(host).is_loopback


def _require_loopback(request: Request) -> None:
    if not _is_loopback(request.client.host if request.client else None):
        raise HTTPException(
            status_code=403,
            detail={"code": "LOCAL_ONLY", "message": "Folder selection is local-only"},
        )


def _invalid_project_path_error() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "INVALID_PROJECT_PATH",
            "message": "Project path must be an existing directory.",
        },
    )


def _validated_project_path(path: str | Path) -> Path:
    try:
        candidate = Path(path).expanduser()
    except (OSError, RuntimeError, ValueError) as exc:
        raise _invalid_project_path_error() from exc
    if not candidate.is_absolute():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PROJECT_PATH_MUST_BE_ABSOLUTE",
                "message": "Project path must be absolute.",
            },
        )

    try:
        selected = candidate.resolve()
        is_directory = selected.is_dir()
    except (OSError, RuntimeError, ValueError) as exc:
        raise _invalid_project_path_error() from exc
    if not is_directory:
        raise _invalid_project_path_error()
    return selected


def _selected_project(path: str | Path) -> ProjectPickResponse:
    selected = _validated_project_path(path)
    return ProjectPickResponse(
        status="selected",
        project=ProjectRef(path=str(selected), name=selected.name),
    )


def create_project_router(picker: FolderPicker | None = None) -> APIRouter:
    chosen_picker = picker or NativeFolderPicker()
    router = APIRouter()

    @router.post("/api/projects/pick")
    def pick_project(request: Request) -> ProjectPickResponse:
        _require_loopback(request)

        try:
            selected = chosen_picker.pick()
        except PickerBusyError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "PICKER_BUSY", "message": str(exc), "recoverable": True},
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "PICKER_UNAVAILABLE", "message": str(exc), "recoverable": True},
            ) from exc
        if selected is None:
            return ProjectPickResponse(status="cancelled", project=None)

        return _selected_project(selected)

    @router.post("/api/projects/select")
    def select_project(request: Request, selection: ProjectSelectRequest) -> ProjectPickResponse:
        _require_loopback(request)
        return _selected_project(selection.path)

    return router
