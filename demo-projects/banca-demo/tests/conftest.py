"""Fixtures compartidas: cada test corre contra una base en memoria y aislada."""

from __future__ import annotations

import pytest

from banca import db


@pytest.fixture()
def conexion():
    conexion = db.conectar(":memory:")
    db.crear_esquema(conexion)
    db.poblar_datos_demo(conexion)
    yield conexion
    conexion.close()


@pytest.fixture()
def usuario_ana(conexion):
    return conexion.execute("SELECT * FROM usuarios WHERE email = 'ana@banca.demo'").fetchone()


@pytest.fixture()
def usuario_luis(conexion):
    return conexion.execute("SELECT * FROM usuarios WHERE email = 'luis@banca.demo'").fetchone()
