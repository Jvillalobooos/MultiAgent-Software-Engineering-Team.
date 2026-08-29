"""Independent acceptance checks, outside the code visible to the Developer agent.

BANCA_DEMO_THROUGH=N selects the cumulative capabilities expected after case N.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent / "banca-demo"
sys.path.insert(0, str(PROJECT))
from banca import auth, cuentas, db, perfil, seguridad, transacciones

THROUGH = int(os.environ.get("BANCA_DEMO_THROUGH", "5"))


@pytest.fixture
def connection():
    conn = db.conectar(":memory:")
    db.crear_esquema(conn)
    db.poblar_datos_demo(conn)
    yield conn
    conn.close()


def row(conn, sql, values=()):
    return conn.execute(sql, values).fetchone()


def expired_value(value, maximum_seconds):
    """Accept ISO/SQLite timestamps or Unix seconds, but verify the actual TTL."""
    try:
        timestamp = float(value)
        expired = 0
    except (TypeError, ValueError):
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        timestamp = parsed.timestamp()
        expired = "2000-01-01" + str(value)[10:]
    assert 0 < timestamp - datetime.now(timezone.utc).timestamp() <= maximum_seconds + 5
    return expired


def test_recovery_is_private_single_use_and_expires(connection):
    assert callable(getattr(auth, "solicitar_recuperacion", None)), "recovery function missing"
    assert callable(getattr(auth, "restablecer_password", None)), "reset function missing"
    known = auth.solicitar_recuperacion(connection, "ana@banca.demo")
    unknown = auth.solicitar_recuperacion(connection, "absent@banca.demo")
    assert known == unknown, "recovery response enumerates accounts"
    token_row = row(connection, "SELECT * FROM tokens_recuperacion WHERE usuario_id=1 ORDER BY rowid DESC")
    token = token_row["token"]
    assert isinstance(token, str) and len(token) >= 32
    assert token not in str(known), "token exposed by recovery response"
    expired_value(token_row["expira_en"], 900)
    auth.restablecer_password(connection, token, "Changed#2026")
    hashed = row(connection, "SELECT password_hash FROM usuarios WHERE id=1")[0]
    assert seguridad.verificar_password("Changed#2026", hashed)
    with pytest.raises((auth.ErrorAutenticacion, ValueError)):
        auth.restablecer_password(connection, token, "Reused#2026")
    auth.solicitar_recuperacion(connection, "ana@banca.demo")
    fresh = row(connection, "SELECT * FROM tokens_recuperacion WHERE usuario_id=1 ORDER BY rowid DESC")
    connection.execute("UPDATE tokens_recuperacion SET expira_en=? WHERE token=?",
                       (expired_value(fresh["expira_en"], 900), fresh["token"]))
    connection.commit()
    with pytest.raises((auth.ErrorAutenticacion, ValueError)):
        auth.restablecer_password(connection, fresh["token"], "Expired#2026")
    assert seguridad.verificar_password("Changed#2026", row(connection, "SELECT password_hash FROM usuarios WHERE id=1")[0])


@pytest.mark.skipif(THROUGH < 2, reason="case 2 not executed")
def test_locking_and_reset_counter(connection):
    for _ in range(4):
        with pytest.raises(auth.ErrorAutenticacion):
            auth.autenticar(connection, "ana@banca.demo", "incorrect")
    assert auth.autenticar(connection, "ana@banca.demo", "Ana#2026")
    assert row(connection, "SELECT intentos_fallidos FROM usuarios WHERE id=1")[0] == 0
    for _ in range(5):
        with pytest.raises(auth.ErrorAutenticacion):
            auth.autenticar(connection, "ana@banca.demo", "incorrect")
    with pytest.raises(auth.ErrorAutenticacion) as locked:
        auth.autenticar(connection, "ana@banca.demo", "Ana#2026")
    with pytest.raises(auth.ErrorAutenticacion) as absent:
        auth.autenticar(connection, "absent@banca.demo", "incorrect")
    assert str(locked.value) == str(absent.value)
    until = row(connection, "SELECT bloqueada_hasta FROM usuarios WHERE id=1")[0]
    connection.execute("UPDATE usuarios SET bloqueada_hasta=? WHERE id=1", (expired_value(until, 900),))
    connection.commit()
    assert auth.autenticar(connection, "ana@banca.demo", "Ana#2026"), "expired lock must release account"


@pytest.fixture
def client(connection, monkeypatch):
    from banca import api
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api, "conexion", connection)
    return TestClient(api.app)


def headers(connection, email="ana@banca.demo", password="Ana#2026"):
    return {"Authorization": "Bearer " + auth.autenticar(connection, email, password)}


def transaction_items(response):
    # The prompt does not prescribe a JSON envelope. The base account endpoint
    # already uses {"transacciones": [...]}; both shapes preserve this contract.
    payload = response.json()
    items = payload.get("transacciones") if isinstance(payload, dict) else payload
    assert isinstance(items, list), "response must contain a transaction list"
    return items


@pytest.mark.skipif(THROUGH < 3, reason="case 3 not executed")
def test_recent_transactions_api_is_owner_scoped_and_bounded(connection, client):
    assert client.get("/api/transacciones/recientes").status_code == 401
    result = client.get("/api/transacciones/recientes?limite=2", headers=headers(connection))
    assert result.status_code == 200
    items = transaction_items(result)
    assert len(items) == 2
    assert [item["id"] for item in items] == [3, 2]
    assert all(item["cuenta_id"] == 1 for item in items)
    for _ in range(105):
        transacciones.registrar(connection, 1, 1, "deposito", 1, "acceptance")
    items = transacciones.transacciones_recientes_de_usuario(connection, 1, 999)
    assert len(items) == transacciones.LIMITE_MAXIMO
    result = client.get("/api/transacciones/recientes", headers=headers(connection, "luis@banca.demo", "Luis#2026"))
    assert result.status_code == 200
    luis_items = transaction_items(result)
    assert len(luis_items) == 2
    assert all(item["cuenta_id"] == 2 for item in luis_items)


@pytest.mark.skipif(THROUGH < 4, reason="case 4 not executed")
def test_profile_api_is_authenticated_validated_and_owner_scoped(connection, client):
    assert client.patch("/api/perfil", json={"nombre": "Mallory"}).status_code == 401
    auth_headers = headers(connection)
    before = perfil.obtener_perfil(connection, 1)
    response = client.patch("/api/perfil", headers=auth_headers, json={"nombre": "Ana Demo"})
    assert response.status_code == 200
    assert response.json()["nombre"] == "Ana Demo"
    assert response.json()["telefono"] == before["telefono"]
    assert "password_hash" not in response.json()
    assert client.patch("/api/perfil", headers=auth_headers, json={"nombre": " "}).status_code in {400, 422}
    assert client.patch("/api/perfil", headers=auth_headers, json={"telefono": "not a phone"}).status_code in {400, 422}
    client.patch("/api/perfil", headers=auth_headers, json={"email": "other@example.com", "usuario_id": 2})
    assert perfil.obtener_perfil(connection, 1)["email"] == before["email"]
    assert perfil.obtener_perfil(connection, 2)["nombre"] == "Luis Mora"


@pytest.mark.skipif(THROUGH < 5, reason="case 5 not executed")
def test_sensitive_transfer_requires_valid_owner_confirmation(connection):
    assert callable(getattr(transacciones, "solicitar_transferencia_alta", None)), "step-up operation missing"
    connection.execute("UPDATE cuentas SET saldo=10000 WHERE id=1")
    connection.commit()
    initial = row(connection, "SELECT COUNT(*) FROM transacciones")[0]
    small = transacciones.solicitar_transferencia_alta(connection, 1, 1, 1000, "CR-0002")
    assert small["estado"] == "completada"
    assert row(connection, "SELECT COUNT(*) FROM transacciones")[0] == initial + 1
    pending = transacciones.solicitar_transferencia_alta(connection, 1, 1, 1100, "CR-0002")
    assert pending["estado"] == "pendiente"
    assert row(connection, "SELECT COUNT(*) FROM transacciones")[0] == initial + 1
    confirmation = row(connection, "SELECT * FROM confirmaciones ORDER BY rowid DESC")
    code = confirmation["codigo"]
    assert len(code) >= 43 and code not in str(pending)
    expired_value(confirmation["expira_en"], 300)
    with pytest.raises((ValueError, PermissionError, cuentas.CuentaNoEncontrada)):
        transacciones.confirmar_transferencia(connection, pending["solicitud_id"], "wrong", 1)
    with pytest.raises((ValueError, PermissionError, cuentas.CuentaNoEncontrada)):
        transacciones.confirmar_transferencia(connection, pending["solicitud_id"], code, 2)
    assert row(connection, "SELECT COUNT(*) FROM transacciones")[0] == initial + 1
    transacciones.confirmar_transferencia(connection, pending["solicitud_id"], code, 1)
    assert row(connection, "SELECT COUNT(*) FROM transacciones")[0] == initial + 2
    with pytest.raises((ValueError, PermissionError, cuentas.CuentaNoEncontrada)):
        transacciones.confirmar_transferencia(connection, pending["solicitud_id"], code, 1)
    next_pending = transacciones.solicitar_transferencia_alta(connection, 1, 1, 1100, "CR-0002")
    latest = row(connection, "SELECT * FROM confirmaciones ORDER BY rowid DESC")
    connection.execute("UPDATE confirmaciones SET expira_en=? WHERE codigo=?",
                       (expired_value(latest["expira_en"], 300), latest["codigo"]))
    connection.commit()
    with pytest.raises((ValueError, PermissionError, cuentas.CuentaNoEncontrada)):
        transacciones.confirmar_transferencia(connection, next_pending["solicitud_id"], latest["codigo"], 1)
    assert row(connection, "SELECT COUNT(*) FROM transacciones")[0] == initial + 2
