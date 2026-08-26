"""Operaciones aritméticas básicas.

Todas las funciones son puras: no mutan sus argumentos ni escriben estado.
El registro de lo ejecutado es responsabilidad de `calculadora.historial`.
"""

from __future__ import annotations

Numero = int | float


def sumar(a: Numero, b: Numero) -> Numero:
    """Devuelve `a + b`."""
    return a + b


def restar(a: Numero, b: Numero) -> Numero:
    """Devuelve `a - b`."""
    return a - b


def multiplicar(a: Numero, b: Numero) -> Numero:
    """Devuelve `a * b`."""
    return a * b


def dividir(a: Numero, b: Numero) -> float:
    """Devuelve `a / b`.

    Lanza `ZeroDivisionError` con un mensaje propio en vez de dejar escapar el
    de CPython: quien llama necesita saber qué operación falló, no solo que
    hubo una división por cero en algún sitio.
    """
    if b == 0:
        raise ZeroDivisionError("No se puede dividir entre cero.")
    return a / b


def potencia(base: Numero, exponente: Numero) -> Numero:
    """Devuelve `base ** exponente`."""
    return base**exponente


def raiz(radicando: Numero, indice: int = 2) -> float:
    """Raíz n-ésima de `radicando`.

    Se rechaza el radicando negativo con índice par porque el resultado no es
    real y devolver un complejo sorprendería a quien usa una calculadora.
    """
    if indice == 0:
        raise ValueError("El índice de la raíz no puede ser cero.")
    if radicando < 0 and indice % 2 == 0:
        raise ValueError("No existe raíz real de índice par para un negativo.")
    if radicando < 0:
        return -((-radicando) ** (1 / indice))
    return radicando ** (1 / indice)


def porcentaje(total: Numero, parte: Numero) -> float:
    """Qué porcentaje representa `parte` sobre `total`."""
    if total == 0:
        raise ZeroDivisionError("El total no puede ser cero.")
    return (parte / total) * 100
