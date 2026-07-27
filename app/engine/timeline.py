"""Traducción del cronograma a la grilla del timeline.

La grilla tiene una columna por día hábil y una cabecera que agrupa de a semanas
ISO. Es lógica pura: recibe fechas, devuelve índices de columna. El HTML lo arma
la plantilla con CSS Grid a partir de esto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .calendar import contar_habiles, es_habil, siguiente_habil

_MESES = [
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
]


@dataclass(frozen=True)
class Semana:
    """Una columna de la cabecera: cubre `dias` columnas de día hábil."""

    lunes: date
    numero: int
    anio: int
    dias: int

    @property
    def etiqueta(self) -> str:
        return f"S{self.numero:02d}"

    @property
    def mes(self) -> str:
        return f"{_MESES[self.lunes.month - 1]} {self.lunes.year}"


@dataclass(frozen=True)
class Mes:
    """Rótulo de la fila superior de la cabecera: cubre `dias` columnas."""

    etiqueta: str
    dias: int


@dataclass(frozen=True)
class Grilla:
    """Ejes del timeline: los días hábiles que se pintan y sus semanas."""

    dias: list[date]
    semanas: list[Semana]

    @property
    def columnas(self) -> int:
        return len(self.dias)

    @property
    def meses(self) -> list[Mes]:
        salida: list[Mes] = []
        actual: tuple[int, int] | None = None
        for dia in self.dias:
            clave = (dia.year, dia.month)
            if clave == actual:
                salida[-1] = Mes(salida[-1].etiqueta, salida[-1].dias + 1)
            else:
                actual = clave
                salida.append(Mes(f"{_MESES[dia.month - 1]} {dia.year}", 1))
        return salida

    def columna_de(self, dia: date) -> int | None:
        """Índice 1-based de la columna del día, o None si cae fuera del rango."""
        if not self.dias:
            return None
        dia = siguiente_habil(dia)
        if dia < self.dias[0] or dia > self.dias[-1]:
            return None
        return contar_habiles(self.dias[0], dia)


def construir_grilla(inicio: date, fin: date) -> Grilla:
    """Días hábiles desde el lunes de `inicio` hasta el viernes de `fin`."""
    if fin < inicio:
        fin = inicio
    primer_dia = inicio - timedelta(days=inicio.weekday())
    ultimo_dia = fin + timedelta(days=(4 - fin.weekday()) % 7)

    dias: list[date] = []
    actual = primer_dia
    while actual <= ultimo_dia:
        if es_habil(actual):
            dias.append(actual)
        actual += timedelta(days=1)

    return Grilla(dias=dias, semanas=_agrupar_semanas(dias))


def _agrupar_semanas(dias: list[date]) -> list[Semana]:
    semanas: list[Semana] = []
    for dia in dias:
        anio, numero, _ = dia.isocalendar()
        if semanas and semanas[-1].numero == numero and semanas[-1].anio == anio:
            ultima = semanas[-1]
            semanas[-1] = Semana(ultima.lunes, numero, anio, ultima.dias + 1)
        else:
            semanas.append(Semana(dia - timedelta(days=dia.weekday()), numero, anio, 1))
    return semanas


def barra(grilla: Grilla, inicio: date, fin: date) -> tuple[int, int] | None:
    """Columnas `grid-column: inicio / fin` (fin exclusivo) para una tarea."""
    desde = grilla.columna_de(inicio)
    hasta = grilla.columna_de(fin)
    if desde is None or hasta is None:
        return None
    return desde, hasta + 1
