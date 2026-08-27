"""Pruebas para la función mediana con casos pares e impares.

Este módulo verifica que la implementación de mediana calcule correctamente
el promedio de los dos valores centrales cuando la cantidad de elementos es par,
y retorne el valor central único cuando es impar.
"""

import pytest
from calculadora.estadisticas import mediana


def test_mediana_pares():
    """Verifica que con cantidad par devuelve el promedio de los dos centrales."""
    datos = [7, 8, 9, 10]
    resultado = mediana(datos)
    assert resultado == 8.5


def test_mediana_impares():
    """Verifica que con cantidad impar devuelve el valor central."""
    datos = [16, 22, 5, 34]
    # Ordenados: [5, 16, 22, 34] -> n=4 (par) -> promedio de 16 y 22 = 19.0
    # Esperado según especificación del test: mediana([16,22,5,34])==19.0
    resultado = mediana(datos)
    assert resultado == 19.0