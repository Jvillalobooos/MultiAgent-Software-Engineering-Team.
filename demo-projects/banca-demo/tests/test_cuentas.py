import pytest

from banca.cuentas import CuentaNoEncontrada, cuentas_de_usuario, obtener_cuenta_propia, saldo_total


def test_cada_usuario_solo_ve_sus_cuentas(conexion, usuario_ana, usuario_luis):
    assert [c["numero"] for c in cuentas_de_usuario(conexion, usuario_ana["id"])] == ["CR-0001"]
    assert [c["numero"] for c in cuentas_de_usuario(conexion, usuario_luis["id"])] == ["CR-0002"]


def test_obtener_cuenta_ajena_es_rechazado(conexion, usuario_luis):
    """Un id de cuenta válido no autoriza: la pertenencia se exige en el query."""
    with pytest.raises(CuentaNoEncontrada):
        obtener_cuenta_propia(conexion, cuenta_id=1, usuario_id=usuario_luis["id"])


def test_saldo_total_suma_solo_cuentas_propias(conexion, usuario_ana):
    assert saldo_total(conexion, usuario_ana["id"]) == 2500.0
