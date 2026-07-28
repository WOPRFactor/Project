"""Qué filas se dibujan del Gantt y de qué color. Módulo puro: sin base ni sesión.

Dos decisiones de presentación, un solo archivo, porque son la misma pregunta desde
dos lados: *qué se ve*.

Dos reglas que no son cosméticas:

1. **El filtro no cambia los totales.** El cronograma se calcula siempre entero —si no,
   las dependencias con las tareas ocultas darían fechas distintas— y el resumen de
   arriba sigue siendo el del proyecto completo. Un Gantt filtrado que además cambiara
   los números de arriba es una captura de pantalla lista para engañar a alguien.
2. **El color nunca es la única señal.** Los modos son excluyentes (dos criterios de
   color a la vez dan barro) y la barra siempre lleva además el título y el tooltip,
   así el Gantt sigue leyéndose impreso en blanco y negro.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — solo el tipo, sin import circular
    from .vista import Fila

TODO = "todo"
ETAPAS = "etapas"

DETALLES = {
    TODO: "Todo el árbol",
    ETAPAS: "Solo etapas e hitos",
    "n1": "Hasta el nivel 2",
    "n2": "Hasta el nivel 3",
}

POR_CRITICIDAD = "criticidad"
POR_ESTADO = "estado"
POR_AMBITO = "ambito"
POR_AVANCE = "avance"

MODOS_COLOR = {
    POR_CRITICIDAD: "Criticidad",
    POR_ESTADO: "Estado",
    POR_AMBITO: "Ámbito",
    POR_AVANCE: "Avance",
}


@dataclass(frozen=True)
class Mirada:
    """Cómo está mirando el usuario la grilla ahora mismo."""

    detalle: str = TODO
    etapa: int | None = None
    color: str = POR_CRITICIDAD

    @property
    def filtrada(self) -> bool:
        return self.detalle != TODO or self.etapa is not None

    def normalizada(self) -> "Mirada":
        """Lo que llega del formulario no se toma como viene."""
        return Mirada(
            detalle=self.detalle if self.detalle in DETALLES else TODO,
            etapa=self.etapa,
            color=self.color if self.color in MODOS_COLOR else POR_CRITICIDAD,
        )


def filtrar(filas: list["Fila"], mirada: Mirada) -> list["Fila"]:
    """Las filas que se dibujan. El cálculo ya se hizo sobre todas."""
    visibles = filas
    if mirada.etapa is not None:
        visibles = _rama(visibles, mirada.etapa)
    if mirada.detalle == ETAPAS:
        # Nivel 0 más los hitos de cualquier profundidad: los hitos son justamente
        # lo que se reporta, esconderlos dejaría la vista de una página sin marcas.
        visibles = [f for f in visibles if f.nivel == 0 or f.es_hito]
    elif mirada.detalle in ("n1", "n2"):
        tope = int(mirada.detalle[1])
        visibles = [f for f in visibles if f.nivel <= tope or f.es_hito]
    return visibles


def _rama(filas: list["Fila"], raiz_id: int) -> list["Fila"]:
    """La etapa elegida y todo lo que cuelga de ella."""
    hijas: dict[int | None, list[int]] = {}
    for fila in filas:
        hijas.setdefault(fila.tarea.parent_id, []).append(fila.tarea.id or 0)

    dentro = {raiz_id}
    pila = list(hijas.get(raiz_id, []))
    while pila:
        actual = pila.pop()
        if actual in dentro:
            continue
        dentro.add(actual)
        pila.extend(hijas.get(actual, []))
    return [f for f in filas if (f.tarea.id or 0) in dentro]


def etapas(filas: list["Fila"]) -> list["Fila"]:
    """Las candidatas del selector de etapa: lo que cuelga de la raíz."""
    return [f for f in filas if f.nivel == 0]


def avance(fila: "Fila") -> int:
    """Cuánto de la barra va pintado. Hoy sale del estado; en la Fase 18, de la tarea."""
    if fila.estado is None:
        return 0
    return max(0, min(100, fila.estado.avance_sugerido))


def clase_color(fila: "Fila", modo: str) -> str:
    """Un tono por fila según el criterio elegido. Los resúmenes no se pintan.

    Una barra de resumen es una envolvente, no trabajo: darle color de estado o de
    avance sugeriría un dato que no tiene.
    """
    if fila.es_resumen:
        return "resumen"
    if modo == POR_ESTADO:
        return f"color-{fila.estado.color.value}" if fila.estado else "color-gris"
    if modo == POR_AMBITO:
        return f"ambito-barra-{fila.tarea.ambito.value}"
    if modo == POR_AVANCE:
        return _por_avance(avance(fila))
    return "critica" if fila.tarea.critica else "color-azul"


def _por_avance(porcentaje: int) -> str:
    if porcentaje >= 100:
        return "color-verde"
    if porcentaje >= 50:
        return "color-azul"
    if porcentaje > 0:
        return "color-ambar"
    return "color-gris"
