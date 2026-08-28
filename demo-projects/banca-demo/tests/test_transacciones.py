import pytest

from banca.cuentas import CuentaNoEncontrada
from banca.transacciones import LIMITE_MAXIMO, registrar, transacciones_de_cuenta


def test_lista_las_transacciones_de_una_cuenta_propia(conexion, usuario_ana):
    filas = transacciones_de_cuenta(conexion, 1, usuario_ana["id"])
    assert len(filas) == 3
    assert {f["tipo"] for f in filas} == {"deposito", "retiro", "transferencia"}


def test_no_devuelve_transacciones_de_otro_usuario(conexion, usuario_luis):
    with pytest.raises(CuentaNoEncontrada):
        transacciones_de_cuenta(conexion, 1, usuario_luis["id"])


def test_el_limite_esta_acotado(conexion, usuario_ana):
    filas = transacciones_de_cuenta(conexion, 1, usuario_ana["id"], limite=LIMITE_MAXIMO * 10)
    assert len(filas) <= LIMITE_MAXIMO


def test_registrar_exige_monto_positivo(conexion, usuario_ana):
    with pytest.raises(ValueError):
        registrar(conexion, 1, usuario_ana["id"], "deposito", 0)


def test_registrar_agrega_el_movimiento(conexion, usuario_ana):
    registrar(conexion, 1, usuario_ana["id"], "deposito", 50.0, "Reintegro")
    assert len(transacciones_de_cuenta(conexion, 1, usuario_ana["id"])) == 4
