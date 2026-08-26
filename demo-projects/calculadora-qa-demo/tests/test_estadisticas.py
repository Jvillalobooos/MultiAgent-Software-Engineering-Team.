"""Pruebas de estadística descriptiva."""

import pytest

from calculadora import estadisticas


def test_media():
    assert estadisticas.media([1, 2, 3, 4]) == 2.5


def test_media_vacia_lanza():
    with pytest.raises(ValueError):
        estadisticas.media([])


def test_mediana_cantidad_impar():
    assert estadisticas.mediana([3, 1, 2]) == 2


def test_mediana_desordenada():
    assert estadisticas.mediana([9, 1, 5]) == 5


def test_moda():
    assert estadisticas.moda([1, 2, 2, 3]) == 2


def test_moda_con_empate_devuelve_el_menor():
    assert estadisticas.moda([4, 4, 7, 7]) == 4


def test_rango():
    assert estadisticas.rango([10, 3, 7]) == 7
