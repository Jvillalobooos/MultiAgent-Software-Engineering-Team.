"""Pruebas de las operaciones aritméticas."""

import pytest

from calculadora import operaciones


def test_sumar():
    assert operaciones.sumar(2, 3) == 5
    assert operaciones.sumar(-1, 1) == 0


def test_restar():
    assert operaciones.restar(10, 4) == 6


def test_multiplicar():
    assert operaciones.multiplicar(3, 4) == 12
    assert operaciones.multiplicar(5, 0) == 0


def test_dividir():
    assert operaciones.dividir(10, 4) == 2.5


def test_dividir_entre_cero_lanza():
    with pytest.raises(ZeroDivisionError):
        operaciones.dividir(1, 0)


def test_potencia():
    assert operaciones.potencia(2, 10) == 1024


def test_raiz_cuadrada():
    assert operaciones.raiz(9) == 3


def test_raiz_cubica_de_negativo():
    assert operaciones.raiz(-27, 3) == pytest.approx(-3)


def test_raiz_par_de_negativo_lanza():
    with pytest.raises(ValueError):
        operaciones.raiz(-4, 2)


def test_porcentaje():
    assert operaciones.porcentaje(200, 50) == 25
