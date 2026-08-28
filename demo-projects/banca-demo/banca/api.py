"""API HTTP. Cada ruta protegida resuelve su actor desde el token de sesión."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from banca import db
from banca.auth import ErrorAutenticacion, autenticar, cerrar_sesion, usuario_de_sesion
from banca.cuentas import CuentaNoEncontrada, cuentas_de_usuario, saldo_total
from banca.perfil import obtener_perfil
from banca.transacciones import transacciones_de_cuenta

ESTATICOS = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Banca Demo", version="0.1.0")
conexion = db.inicializar()


class CredencialesEntrada(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


def actor_autenticado(authorization: str = Header(default="")):
    """Resuelve el usuario autenticado; 401 uniforme si el token no es válido."""
    token = authorization.removeprefix("Bearer ").strip()
    usuario = usuario_de_sesion(conexion, token) if token else None
    if usuario is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    return usuario


@app.post("/api/login")
def login(credenciales: CredencialesEntrada) -> dict[str, str]:
    try:
        return {"token": autenticar(conexion, credenciales.email, credenciales.password)}
    except ErrorAutenticacion:
        raise HTTPException(status_code=401, detail="Credenciales inválidas") from None


@app.post("/api/logout")
def logout(authorization: str = Header(default="")) -> dict[str, str]:
    cerrar_sesion(conexion, authorization.removeprefix("Bearer ").strip())
    return {"estado": "sesion cerrada"}


@app.get("/api/perfil")
def leer_perfil(usuario=Depends(actor_autenticado)) -> dict[str, object]:
    perfil = obtener_perfil(conexion, usuario["id"])
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return perfil


@app.get("/api/cuentas")
def listar_cuentas(usuario=Depends(actor_autenticado)) -> dict[str, object]:
    filas = cuentas_de_usuario(conexion, usuario["id"])
    return {
        "total": saldo_total(conexion, usuario["id"]),
        "cuentas": [dict(fila) for fila in filas],
    }


@app.get("/api/cuentas/{cuenta_id}/transacciones")
def listar_transacciones(
    cuenta_id: int, limite: int = 20, usuario=Depends(actor_autenticado)
) -> dict[str, object]:
    try:
        filas = transacciones_de_cuenta(conexion, cuenta_id, usuario["id"], limite)
    except CuentaNoEncontrada:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada") from None
    return {"cuenta_id": cuenta_id, "transacciones": [dict(fila) for fila in filas]}


@app.get("/")
def inicio() -> FileResponse:
    return FileResponse(ESTATICOS / "index.html")


app.mount("/static", StaticFiles(directory=str(ESTATICOS)), name="static")
