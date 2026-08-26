"""Registro en memoria de las operaciones ejecutadas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Entrada:
    """Una operación ya ejecutada y su resultado."""

    operacion: str
    argumentos: tuple[float, ...]
    resultado: float

    def __str__(self) -> str:
        args = ", ".join(str(a) for a in self.argumentos)
        return f"{self.operacion}({args}) = {self.resultado}"


@dataclass
class Historial:
    """Cola acotada de operaciones.

    El límite existe para que una sesión larga no crezca sin control; al
    superarlo se descarta la entrada más antigua.
    """

    limite: int = 50
    _entradas: list[Entrada] = field(default_factory=list)

    def registrar(self, operacion: str, argumentos: tuple[float, ...], resultado: float) -> Entrada:
        entrada = Entrada(operacion, argumentos, resultado)
        self._entradas.append(entrada)
        if len(self._entradas) > self.limite:
            self._entradas.pop(0)
        return entrada

    @property
    def entradas(self) -> list[Entrada]:
        return list(self._entradas)

    def ultima(self) -> Entrada | None:
        return self._entradas[-1] if self._entradas else None

    def limpiar(self) -> None:
        self._entradas.clear()

    def __len__(self) -> int:
        return len(self._entradas)
