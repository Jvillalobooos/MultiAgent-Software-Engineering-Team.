from fastapi import FastAPI, HTTPException

from .service import BankService

app = FastAPI(title="Sample Bank App")
service = BankService(":memory:")


@app.get("/transactions/{user_id}")
def transactions(user_id: str, authorized_user: str) -> dict[str, list[int]]:
    try:
        return {"transactions": service.history(authorized_user, user_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
