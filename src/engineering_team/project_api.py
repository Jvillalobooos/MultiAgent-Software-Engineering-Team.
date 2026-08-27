"""Local-only HTTP transport for selecting a project directory."""

from __future__ import annotations

import ipaddress
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from engineering_team.project_picker import FolderPicker, WindowsFolderPicker


class ProjectRef(BaseModel):
    path: str
    name: str


class ProjectPickResponse(BaseModel):
    status: Literal["selected", "cancelled"]
    project: ProjectRef | None


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    return ipaddress.ip_address(host).is_loopback


def create_project_router(picker: FolderPicker | None = None) -> APIRouter:
    chosen_picker = picker or WindowsFolderPicker()
    router = APIRouter()

    @router.post("/api/projects/pick")
    def pick_project(request: Request) -> ProjectPickResponse:
        if not _is_loopback(request.client.host if request.client else None):
            raise HTTPException(
                status_code=403,
                detail={"code": "LOCAL_ONLY", "message": "Folder selection is local-only"},
            )

        selected = chosen_picker.pick()
        if selected is None:
            return ProjectPickResponse(status="cancelled", project=None)

        selected = selected.resolve()
        if not selected.is_dir():
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_PROJECT", "message": "Selected path is not a directory"},
            )

        return ProjectPickResponse(
            status="selected",
            project=ProjectRef(path=str(selected), name=selected.name),
        )

    return router
