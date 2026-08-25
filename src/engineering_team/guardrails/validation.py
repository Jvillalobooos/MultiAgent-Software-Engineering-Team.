from pydantic import BaseModel


def validate_output(model_type: type[BaseModel], payload: object) -> BaseModel:
    return model_type.model_validate(payload)


def require_explicit_destructive_authorization(authorized: bool) -> None:
    if not authorized:
        raise PermissionError("destructive operation requires explicit authorization")
