"""Estadística descriptiva sobre secuencias de números.

Todas las funciones rechazan la secuencia vacía en vez de devolver un valor
inventado: no hay media de cero elementos, y devolver 0 sería mentir.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

Numero = int | float


def _validar(datos: Sequence[Numero]) -> None:
    if not datos:
        raise ValueError("La secuencia no puede estar vacía.")


def media(datos: Sequence[Numero]) -> float:
    """Media aritmética de `datos`."""
    _validar(datos)
    return sum(datos) / len(datos)


def mediana(datos: Sequence[Numero]) -> float:
    """Valor central de `datos` una vez ordenados.

    Con una cantidad IMPAR de elementos es el elemento del medio. Con una
    cantidad PAR es el promedio de los dos elementos centrales, porque en ese
    caso no hay un único centro.
    """
    _validar(datos)
    ordenados = sorted(datos)
    medio = len(ordenados) // 2
    return ordenados[medio]


def moda(datos: Sequence[Numero]) -> Numero:
    """Valor más frecuente. Con empate devuelve el menor, por determinismo."""
    _validar(datos)
    frecuencias = Counter(datos)
    mayor = max(frecuencias.values())
    return min(valor for valor, veces in frecuencias.items() if veces == mayor)


def rango(datos: Sequence[Numero]) -> Numero:
    """Diferencia entre el máximo y el mínimo."""
    _validar(datos)
    return max(datos) - min(datos)
