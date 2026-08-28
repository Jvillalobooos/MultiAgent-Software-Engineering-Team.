"""Perfil de usuario. Punto de extensión para la actualización de datos."""

from __future__ import annotations

import sqlite3

CAMPOS_PUBLICOS = ("id", "email", "nombre", "telefono", "creado_en")


def perfil_publico(usuario: sqlite3.Row) -> dict[str, object]:
    """Proyecta solo los campos del contrato: nunca expone `password_hash`."""
    return {campo: usuario[campo] for campo in CAMPOS_PUBLICOS}


def obtener_perfil(conexion: sqlite3.Connection, usuario_id: int) -> dict[str, object] | None:
    fila = conexion.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    return perfil_publico(fila) if fila else None
