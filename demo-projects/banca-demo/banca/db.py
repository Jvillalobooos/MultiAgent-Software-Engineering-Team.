"""Acceso a SQLite. Una sola conexión por proceso, esquema creado al iniciar."""

from __future__ import annotations

import sqlite3
from pathlib import Path

RUTA_DB = Path(__file__).resolve().parent.parent / "banca.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    nombre        TEXT NOT NULL,
    telefono      TEXT,
    password_hash TEXT NOT NULL,
    creado_en     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cuentas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    numero     TEXT NOT NULL UNIQUE,
    saldo      REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS transacciones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cuenta_id   INTEGER NOT NULL REFERENCES cuentas(id),
    tipo        TEXT NOT NULL CHECK (tipo IN ('deposito', 'retiro', 'transferencia')),
    monto       REAL NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    creada_en   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sesiones (
    token      TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    creada_en  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def conectar(ruta: Path | str | None = None) -> sqlite3.Connection:
    """Abre una conexión con claves foráneas activas y filas por nombre."""
    conexion = sqlite3.connect(str(ruta or RUTA_DB), check_same_thread=False)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def crear_esquema(conexion: sqlite3.Connection) -> None:
    conexion.executescript(ESQUEMA)
    conexion.commit()


def poblar_datos_demo(conexion: sqlite3.Connection) -> None:
    """Inserta el juego de datos mínimo. Idempotente."""
    from banca.seguridad import hash_password

    if conexion.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
        return
    usuarios = [
        ("ana@banca.demo", "Ana Rivera", "+506 8888 1111", hash_password("Ana#2026")),
        ("luis@banca.demo", "Luis Mora", "+506 8888 2222", hash_password("Luis#2026")),
    ]
    conexion.executemany(
        "INSERT INTO usuarios (email, nombre, telefono, password_hash) VALUES (?, ?, ?, ?)",
        usuarios,
    )
    conexion.executemany(
        "INSERT INTO cuentas (usuario_id, numero, saldo) VALUES (?, ?, ?)",
        [(1, "CR-0001", 2500.0), (2, "CR-0002", 830.5)],
    )
    conexion.executemany(
        "INSERT INTO transacciones (cuenta_id, tipo, monto, descripcion) VALUES (?, ?, ?, ?)",
        [
            (1, "deposito", 1500.0, "Salario"),
            (1, "retiro", 200.0, "Cajero"),
            (1, "transferencia", 120.0, "Pago servicios"),
            (2, "deposito", 900.0, "Salario"),
            (2, "retiro", 69.5, "Farmacia"),
        ],
    )
    conexion.commit()


def inicializar(ruta: Path | str | None = None) -> sqlite3.Connection:
    conexion = conectar(ruta)
    crear_esquema(conexion)
    poblar_datos_demo(conexion)
    return conexion
