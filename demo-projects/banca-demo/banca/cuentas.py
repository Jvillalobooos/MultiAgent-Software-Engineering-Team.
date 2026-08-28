"""Cuentas bancarias, siempre consultadas dentro del alcance de su dueño."""

from __future__ import annotations

import sqlite3


class CuentaNoEncontrada(Exception):
    """La cuenta no existe o no pertenece al actor autenticado."""


def cuentas_de_usuario(conexion: sqlite3.Connection, usuario_id: int) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM cuentas WHERE usuario_id = ? ORDER BY id", (usuario_id,)
    ).fetchall()


def obtener_cuenta_propia(
    conexion: sqlite3.Connection, cuenta_id: int, usuario_id: int
) -> sqlite3.Row:
    """Consulta con alcance de dueño: la pertenencia se aplica en el propio query.

    Recibir un `cuenta_id` no constituye autorización; el filtro por `usuario_id`
    es lo que la otorga.
    """
    fila = conexion.execute(
        "SELECT * FROM cuentas WHERE id = ? AND usuario_id = ?", (cuenta_id, usuario_id)
    ).fetchone()
    if fila is None:
        raise CuentaNoEncontrada("Cuenta no encontrada")
    return fila


def saldo_total(conexion: sqlite3.Connection, usuario_id: int) -> float:
    fila = conexion.execute(
        "SELECT COALESCE(SUM(saldo), 0.0) AS total FROM cuentas WHERE usuario_id = ?",
        (usuario_id,),
    ).fetchone()
    return float(fila["total"])
