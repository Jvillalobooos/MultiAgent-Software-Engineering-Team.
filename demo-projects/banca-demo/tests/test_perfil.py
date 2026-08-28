from banca.perfil import obtener_perfil, perfil_publico


def test_el_perfil_publico_no_expone_el_hash(conexion, usuario_ana):
    publico = perfil_publico(usuario_ana)
    assert "password_hash" not in publico
    assert publico["email"] == "ana@banca.demo"


def test_obtener_perfil_devuelve_none_si_no_existe(conexion):
    assert obtener_perfil(conexion, 9999) is None
