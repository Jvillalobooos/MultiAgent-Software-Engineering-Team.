"""Transacciones. Punto de extensión para el historial reciente."""

from __future__ import annotations

import sqlite3

from banca.cuentas import obtener_cuenta_propia

LIMITE_MAXIMO = 100


def registrar(
    conexion: sqlite3.Connection,
    cuenta_id: int,
    usuario_id: int,
    tipo: str,
    monto: float,
    descripcion: str = "",
) -> int:
    """Registra un movimiento sobre una cuenta del actor autenticado."""
    if monto <= 0:
        raise ValueError("El monto debe ser positivo")
    obtener_cuenta_propia(conexion, cuenta_id, usuario_id)
    cursor = conexion.execute(
        "INSERT INTO transacciones (cuenta_id, tipo, monto, descripcion) VALUES (?, ?, ?, ?)",
        (cuenta_id, tipo, monto, descripcion),
    )
    conexion.commit()
    return int(cursor.lastrowid)


def transacciones_de_cuenta(
    conexion: sqlite3.Connection, cuenta_id: int, usuario_id: int, limite: int = 20
) -> list[sqlite3.Row]:
    """Movimientos de una cuenta propia, más recientes primero.

    La autorización se aplica antes del límite, para que el filtro no pueda
    ocultar un query inseguro.
    """
    obtener_cuenta_propia(conexion, cuenta_id, usuario_id)
    limite = max(1, min(int(limite), LIMITE_MAXIMO))
    return conexion.execute(
        """SELECT * FROM transacciones
           WHERE cuenta_id = ?
           ORDER BY datetime(creada_en) DESC, id DESC
           LIMIT ?""",
        (cuenta_id, limite),
    ).fetchall()
