"""Carga de trabajo por persona: cuánto tiene encima cada una.

Es la pregunta que los contactos vinieron a habilitar. Vive acá y no en el router
porque es lógica de negocio: el router solo la pide y la pinta.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from ..models import Contacto
from . import contactos as contactos_service
from .resumen import esta_hecha


@dataclass
class Carga:
    """Cuánto tiene encima una persona. Es la pregunta que antes no se podía hacer."""

    contacto: Contacto | None
    tareas: int = 0
    hitos: int = 0
    esfuerzo: int = 0
    hechas: int = 0
    atrasadas: int = 0
    sin_margen: int = 0

    @property
    def avance(self) -> int:
        return round(100 * self.hechas / self.tareas) if self.tareas else 0


def cargas(session: Session, project_id: int, datos) -> list[Carga]:
    """Una fila por persona, más una para lo que quedó sin asignar.

    `datos` es la `VistaProyecto` ya armada: las cuentas salen de las mismas filas
    que ve la grilla, así los dos lugares nunca difieren.
    """
    por_contacto: dict[int | None, Carga] = {}
    for contacto in contactos_service.listar(session, project_id):
        por_contacto[contacto.id] = Carga(contacto=contacto)
    por_contacto.setdefault(None, Carga(contacto=None))

    for fila in datos.todas_las_filas:
        if fila.es_resumen:
            continue
        clave = fila.responsable.id if fila.responsable else None
        carga = por_contacto.setdefault(clave, Carga(contacto=fila.responsable))
        if fila.es_hito:
            carga.hitos += 1
        else:
            carga.tareas += 1
            carga.esfuerzo += fila.tarea.duracion
        if esta_hecha(fila):
            carga.hechas += 1
        if fila.desvio is not None and fila.desvio > 0:
            carga.atrasadas += 1
        if fila.sin_holgura and not esta_hecha(fila):
            carga.sin_margen += 1

    salida = list(por_contacto.values())
    # Lo sin asignar al final: es un pendiente, no una persona.
    salida.sort(key=lambda c: (c.contacto is None, -c.esfuerzo))
    return [c for c in salida if c.tareas or c.hitos or c.contacto is not None]
