"""Pruebas del registro de operaciones."""

from calculadora.historial import Historial


def test_registrar_incrementa():
    h = Historial()
    h.registrar("sumar", (2, 3), 5)
    assert len(h) == 1
    assert h.ultima().resultado == 5


def test_formato_legible():
    h = Historial()
    entrada = h.registrar("sumar", (2, 3), 5)
    assert str(entrada) == "sumar(2, 3) = 5"


def test_respeta_el_limite():
    h = Historial(limite=2)
    for i in range(5):
        h.registrar("sumar", (i, i), i + i)
    assert len(h) == 2
    assert h.entradas[0].argumentos == (3, 3)


def test_limpiar():
    h = Historial()
    h.registrar("sumar", (1, 1), 2)
    h.limpiar()
    assert len(h) == 0
    assert h.ultima() is None
