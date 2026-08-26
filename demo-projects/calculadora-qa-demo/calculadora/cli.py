"""Interfaz de línea de comandos de la calculadora."""

from __future__ import annotations

import argparse
import sys

from calculadora import estadisticas, operaciones
from calculadora.historial import Historial

BINARIAS = {
    "sumar": operaciones.sumar,
    "restar": operaciones.restar,
    "multiplicar": operaciones.multiplicar,
    "dividir": operaciones.dividir,
    "potencia": operaciones.potencia,
    "porcentaje": operaciones.porcentaje,
}

AGREGADAS = {
    "media": estadisticas.media,
    "mediana": estadisticas.mediana,
    "moda": estadisticas.moda,
    "rango": estadisticas.rango,
}


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calculadora", description="Calculadora modular.")
    parser.add_argument("operacion", choices=[*BINARIAS, *AGREGADAS])
    parser.add_argument("numeros", nargs="+", type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    historial = Historial()
    try:
        if args.operacion in BINARIAS:
            if len(args.numeros) != 2:
                print(f"'{args.operacion}' necesita exactamente 2 números.", file=sys.stderr)
                return 2
            resultado = BINARIAS[args.operacion](*args.numeros)
        else:
            resultado = AGREGADAS[args.operacion](args.numeros)
    except (ValueError, ZeroDivisionError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    historial.registrar(args.operacion, tuple(args.numeros), resultado)
    print(historial.ultima())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
