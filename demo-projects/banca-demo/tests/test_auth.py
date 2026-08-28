import pytest

from banca.auth import ErrorAutenticacion, autenticar, cerrar_sesion, usuario_de_sesion


def test_autenticar_devuelve_token_con_credenciales_validas(conexion):
    token = autenticar(conexion, "ana@banca.demo", "Ana#2026")
    assert token
    assert usuario_de_sesion(conexion, token)["email"] == "ana@banca.demo"


def test_autenticar_rechaza_password_incorrecta(conexion):
    with pytest.raises(ErrorAutenticacion):
        autenticar(conexion, "ana@banca.demo", "incorrecta")


def test_no_permite_enumeracion_de_cuentas(conexion):
    """El mensaje es el mismo exista o no el email."""
    with pytest.raises(ErrorAutenticacion) as inexistente:
        autenticar(conexion, "nadie@banca.demo", "x")
    with pytest.raises(ErrorAutenticacion) as existente:
        autenticar(conexion, "ana@banca.demo", "x")
    assert str(inexistente.value) == str(existente.value)


def test_cerrar_sesion_invalida_el_token(conexion):
    token = autenticar(conexion, "ana@banca.demo", "Ana#2026")
    cerrar_sesion(conexion, token)
    assert usuario_de_sesion(conexion, token) is None
