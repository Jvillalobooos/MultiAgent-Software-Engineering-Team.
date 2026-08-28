from banca.seguridad import generar_token, hash_password, verificar_password


def test_el_hash_no_guarda_la_contrasena_en_claro():
    almacenado = hash_password("Ana#2026")
    assert "Ana#2026" not in almacenado
    assert almacenado.count("$") == 1


def test_verificar_password_acepta_la_correcta_y_rechaza_la_incorrecta():
    almacenado = hash_password("Ana#2026")
    assert verificar_password("Ana#2026", almacenado) is True
    assert verificar_password("otra", almacenado) is False


def test_verificar_password_rechaza_un_hash_malformado():
    assert verificar_password("x", "sin-separador") is False


def test_los_tokens_son_unicos_y_de_alta_entropia():
    tokens = {generar_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 32 for t in tokens)
