from fastapi import FastAPI, HTTPException

from engineering_team.project_api import create_project_router
from engineering_team.run_api import router as runs_router

from .service import BankService

app = FastAPI(title="Sample Bank App")
app.include_router(create_project_router())
app.include_router(runs_router)
service = BankService(":memory:")


@app.get("/transactions/{user_id}")
def transactions(user_id: str, authorized_user: str) -> dict[str, list[int]]:
    try:
        return {"transactions": service.history(authorized_user, user_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
