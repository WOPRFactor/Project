"""Puente entre el reparto de pesos (puro) y las tareas guardadas.

`pesos.py` no conoce la base a propósito: es aritmética sobre el árbol y se testea
sin sesión. Acá se lee, se llama a esa aritmética y se escribe. Nada más.
"""

from __future__ import annotations

from sqlmodel import Session

from ..models import Task
from . import pesos as pesos_service
from . import tasks as tasks_service

PAREJO = "parejo"
POR_DURACION = "duracion"


def repartir(session: Session, project_id: int, criterio: str = PAREJO) -> int:
    """Reescribe los pesos de todos los niveles. Devuelve cuántas tareas tocó.

    Es un **punto de partida**, no una respuesta: pisa lo que haya cargado, y por eso
    del lado de la UI la acción pide confirmación. El valor de negocio no es
    proporcional a la duración —una firma de acta dura un día y vale meses— así que
    lo que sale de acá se corrige a mano.
    """
    hermanas: dict[int | None, list[Task]] = {}
    for tarea, _ in tasks_service.arbol(session, project_id):
        hermanas.setdefault(tarea.parent_id, []).append(tarea)

    cambiadas = 0
    for grupo in hermanas.values():
        if criterio == POR_DURACION:
            nuevos = pesos_service.repartir_por_duracion([t.duracion for t in grupo])
        else:
            nuevos = pesos_service.repartir_parejo(len(grupo))
        for tarea, peso in zip(grupo, nuevos):
            if tarea.peso != peso:
                tarea.peso = peso
                session.add(tarea)
                cambiadas += 1

    session.commit()
    return cambiadas


def limpiar(session: Session, project_id: int) -> int:
    """Borra todos los pesos declarados: vuelve al reparto automático parejo."""
    cambiadas = 0
    for tarea, _ in tasks_service.arbol(session, project_id):
        if tarea.peso is not None:
            tarea.peso = None
            session.add(tarea)
            cambiadas += 1
    session.commit()
    return cambiadas
