"""Primitivas de seguridad: hashing de contraseñas y generación de tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERACIONES = 120_000
_ALGORITMO = "sha256"


def hash_password(password: str) -> str:
    """Deriva la contraseña con PBKDF2 y devuelve `salt$hash` en hexadecimal."""
    salt = secrets.token_hex(16)
    derivada = hashlib.pbkdf2_hmac(_ALGORITMO, password.encode(), bytes.fromhex(salt), _ITERACIONES)
    return f"{salt}${derivada.hex()}"


def verificar_password(password: str, almacenado: str) -> bool:
    """Compara en tiempo constante para no filtrar información por temporización."""
    try:
        salt, esperado = almacenado.split("$", 1)
    except ValueError:
        return False
    derivada = hashlib.pbkdf2_hmac(_ALGORITMO, password.encode(), bytes.fromhex(salt), _ITERACIONES)
    return hmac.compare_digest(derivada.hex(), esperado)


def generar_token(bytes_entropia: int = 32) -> str:
    """Token de alta entropía apto para sesiones y flujos sensibles."""
    return secrets.token_urlsafe(bytes_entropia)
