"""Cuánto dura y cuánto avanzó un bloque de tareas.

Se separó de `vista.py` cuando ese archivo pasó el techo de 300 líneas, y la línea
por donde se cortó no fue el conteo sino la responsabilidad: `vista` arma las filas
y las barras del timeline; acá se hacen las cuentas que van arriba de la grilla.

Dos unidades que nunca se suman entre sí: la **ventana** es calendario (las de
distintos ámbitos se superponen) y el **esfuerzo** es trabajo (tareas en paralelo
suman esfuerzo pero no estiran la ventana).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from ..engine.calendar import contar_habiles
from ..models import ETIQUETA_AMBITO, Ambito
from . import pesos as pesos_service

if TYPE_CHECKING:  # pragma: no cover — solo para el tipo, sin import circular
    from .vista import Fila


@dataclass
class Resumen:
    """Cuánto dura un bloque de tareas según el cronograma de este momento.

    Hay uno por ámbito más el total: el acompañamiento posterior no tiene por qué
    inflar la duración del alcance comprometido, pero tampoco desaparecer.
    """

    etiqueta: str = "Total"
    inicio: date | None = None
    fin: date | None = None
    dias_habiles: int = 0
    dias_corridos: int = 0
    tareas: int = 0
    hitos: int = 0
    hechas: int = 0
    # Suma de las duraciones de las tareas del bloque. Es *trabajo*, no calendario:
    # tareas en paralelo suman acá pero no estiran la ventana.
    esfuerzo: int = 0

    @property
    def semanas(self) -> int:
        return -(-self.dias_habiles // 5)  # redondeo hacia arriba

    @property
    def avance(self) -> int:
        """Por cabezas. El que importa es el ponderado; este queda como referencia."""
        return round(100 * self.hechas / self.tareas) if self.tareas else 0


@dataclass(frozen=True)
class NivelAbierto:
    """Un grupo de hermanas cuyos pesos no dan 100. Se avisa, no se bloquea."""

    titulo: str
    diferencia: int
    sin_reparto: bool

    @property
    def mensaje(self) -> str:
        if self.sin_reparto:
            return f"{self.titulo}: ya está repartido al 100 y quedan tareas sin peso"
        if self.diferencia < 0:
            return f"{self.titulo}: faltan {-self.diferencia} puntos"
        return f"{self.titulo}: sobran {self.diferencia} puntos"


def esta_hecha(fila: "Fila") -> bool:
    """Único lugar donde se decide si una tarea está terminada.

    El estado lo define el usuario y puede llamarse como quiera; lo que cuenta es
    que ese estado esté marcado como final.
    """
    return fila.estado is not None and fila.estado.es_final


def armar(
    filas: list["Fila"], etiqueta: str, inicio: date | None, fin: date | None
) -> Resumen:
    """Duración de un bloque: se recalcula sola al agregar o quitar tareas."""
    hojas = [f for f in filas if not f.es_resumen]
    return Resumen(
        etiqueta=etiqueta,
        inicio=inicio,
        fin=fin,
        dias_habiles=contar_habiles(inicio, fin) if inicio and fin else 0,
        dias_corridos=(fin - inicio).days + 1 if inicio and fin else 0,
        tareas=len([f for f in hojas if not f.es_hito]),
        hitos=len([f for f in hojas if f.es_hito]),
        hechas=len([f for f in hojas if esta_hecha(f)]),
        esfuerzo=sum(f.tarea.duracion for f in hojas),
    )


def por_ambito(filas: list["Fila"]) -> list[Resumen]:
    """Un contador por ámbito que tenga tareas, en el orden del enum."""
    salida = []
    for ambito in Ambito:
        del_ambito = [f for f in filas if not f.es_resumen and f.tarea.ambito == ambito]
        if not del_ambito:
            continue
        fechas = [(f.inicio, f.fin) for f in del_ambito if f.inicio and f.fin]
        if not fechas:
            continue
        salida.append(armar(
            del_ambito,
            ETIQUETA_AMBITO[ambito],
            min(i for i, _ in fechas),
            max(f for _, f in fechas),
        ))
    return salida


def proximo_hito(filas: list["Fila"], hoy: date) -> "Fila | None":
    """El primer hito que todavía no pasó. Es lo que se mira un martes a la mañana."""
    pendientes = [
        f for f in filas
        if f.es_hito and f.fin and f.fin >= hoy and not esta_hecha(f)
    ]
    if pendientes:
        return min(pendientes, key=lambda f: f.fin)
    futuros = [f for f in filas if f.es_hito and f.fin]
    return max(futuros, key=lambda f: f.fin) if futuros else None


def niveles_abiertos(
    nodos: list[pesos_service.NodoPeso], filas: list["Fila"]
) -> list[NivelAbierto]:
    """Los grupos de hermanas cuya cuenta no da 100, con nombre para poder buscarlos."""
    titulos = {f.tarea.id: f.tarea.titulo for f in filas}
    return [
        NivelAbierto(
            titulo=titulos.get(nivel.parent_id, "Nivel principal"),
            diferencia=nivel.diferencia,
            sin_reparto=nivel.sin_reparto,
        )
        for nivel in pesos_service.niveles(nodos)
        if not nivel.cierra or nivel.sin_reparto
    ]
