"""Autenticación: login y sesiones.

Punto de extensión para bloqueo de cuenta y recuperación de contraseña.
Las reglas de negocio vigentes viven en `knowledge/security-guidelines.md`.
"""

from __future__ import annotations

import sqlite3

from banca.seguridad import generar_token, verificar_password


class ErrorAutenticacion(Exception):
    """Credenciales inválidas. El mensaje nunca revela si el email existe."""


def buscar_usuario_por_email(conexion: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM usuarios WHERE email = ?", (email.strip().lower(),)
    ).fetchone()


def autenticar(conexion: sqlite3.Connection, email: str, password: str) -> str:
    """Valida credenciales y devuelve un token de sesión.

    Responde igual ante email inexistente y contraseña incorrecta para no
    permitir enumeración de cuentas.
    """
    usuario = buscar_usuario_por_email(conexion, email)
    if usuario is None or not verificar_password(password, usuario["password_hash"]):
        raise ErrorAutenticacion("Credenciales inválidas")

    token = generar_token()
    conexion.execute(
        "INSERT INTO sesiones (token, usuario_id) VALUES (?, ?)", (token, usuario["id"])
    )
    conexion.commit()
    return token


def usuario_de_sesion(conexion: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    """Resuelve el actor autenticado a partir del token de sesión."""
    return conexion.execute(
        """SELECT u.* FROM usuarios u
           JOIN sesiones s ON s.usuario_id = u.id
           WHERE s.token = ?""",
        (token,),
    ).fetchone()


def cerrar_sesion(conexion: sqlite3.Connection, token: str) -> None:
    conexion.execute("DELETE FROM sesiones WHERE token = ?", (token,))
    conexion.commit()
