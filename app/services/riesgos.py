"""Riesgos del proyecto: alta, edición y borrado.

La aritmética de la matriz vive en `matriz.py`, los controles del registro en
`riesgos_alertas.py` y el armado de la pantalla en `riesgos_panel.py`; ninguno de
los tres toca la base. Acá se lee y se escribe.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import Riesgo, Task
from . import contactos as contactos_service
from .riesgos_panel import Panel, armar as panel  # noqa: F401 — API del service


class RiesgoInvalido(Exception):
    """Operación rechazada; el mensaje se le muestra al usuario."""


def listar(session: Session, project_id: int) -> list[Riesgo]:
    riesgos = list(session.exec(select(Riesgo).where(Riesgo.project_id == project_id)))
    # Lo más severo primero: es el orden en que se mira una lista de riesgos. Manda
    # el residual, que es el riesgo que se corre de verdad; el inherente desempata.
    riesgos.sort(key=lambda r: (-r.severidad_residual, -r.severidad, r.id or 0))
    return riesgos


def obtener(session: Session, riesgo_id: int) -> Riesgo | None:
    return session.get(Riesgo, riesgo_id)


def de_tarea(session: Session, task_id: int) -> list[Riesgo]:
    return list(session.exec(select(Riesgo).where(Riesgo.task_id == task_id)))


def ids_con_riesgo(session: Session, project_id: int) -> set[int]:
    """Qué tareas tienen al menos un riesgo. Es lo que tilda la grilla."""
    return {
        r.task_id for r in listar(session, project_id) if r.task_id is not None
    }


def crear(session: Session, project_id: int, datos, task_id: int | None = None) -> Riesgo:
    if task_id is not None and not _tarea_del_proyecto(session, project_id, task_id):
        raise RiesgoInvalido("Esa tarea no es de este proyecto")

    riesgo = Riesgo(project_id=project_id, task_id=task_id, **_valores(datos))
    _asignar(session, project_id, riesgo, datos)
    session.add(riesgo)
    session.commit()
    session.refresh(riesgo)
    return riesgo


def actualizar(session: Session, riesgo_id: int, datos) -> Riesgo:
    riesgo = session.get(Riesgo, riesgo_id)
    if riesgo is None:
        raise RiesgoInvalido("Ese riesgo ya no existe")
    for campo, valor in _valores(datos).items():
        setattr(riesgo, campo, valor)
    _asignar(session, riesgo.project_id, riesgo, datos)
    session.add(riesgo)
    session.commit()
    session.refresh(riesgo)
    return riesgo


# El responsable llega como texto y sale como persona del proyecto; la tarea de
# mitigación se valida contra el proyecto. Los dos se resuelven aparte del volcado
# directo de campos.
_APARTE = {"responsable", "mitigacion_task_id"}


def _valores(datos) -> dict:
    return datos.model_dump(exclude=_APARTE)


def _asignar(session: Session, project_id: int, riesgo: Riesgo, datos) -> None:
    riesgo.responsable_id = contactos_service.resolver(
        session, project_id, datos.responsable
    )
    tarea_id = datos.mitigacion_task_id
    if tarea_id is not None and not _tarea_del_proyecto(session, project_id, tarea_id):
        raise RiesgoInvalido("Esa tarea de mitigación no es de este proyecto")
    riesgo.mitigacion_task_id = tarea_id


def eliminar(session: Session, riesgo_id: int) -> bool:
    riesgo = session.get(Riesgo, riesgo_id)
    if riesgo is None:
        return False
    session.delete(riesgo)
    session.commit()
    return True


def marcar_tarea(session: Session, project_id: int, task_id: int, tildado: bool) -> str:
    """El tilde de la grilla. Crea un borrador o saca el que todavía está vacío.

    Destildar **no borra trabajo**: si el riesgo ya tiene descripción, la operación se
    rechaza con un mensaje y el borrado queda para el panel, que es donde se ve lo que
    se está por perder.
    """
    if not _tarea_del_proyecto(session, project_id, task_id):
        raise RiesgoInvalido("Esa tarea no es de este proyecto")

    existentes = de_tarea(session, task_id)
    if tildado:
        if existentes:
            return ""
        crear_borrador(session, project_id, task_id)
        return "Riesgo marcado: completá probabilidad, impacto y mitigación en «Riesgos»"

    cargados = [r for r in existentes if r.descripcion.strip()]
    if cargados:
        raise RiesgoInvalido(
            f"Esa tarea tiene {len(cargados)} riesgo(s) con contenido: borralos desde "
            "«Riesgos» para no perderlos sin querer"
        )
    for riesgo in existentes:
        session.delete(riesgo)
    session.commit()
    return ""


def crear_borrador(session: Session, project_id: int, task_id: int) -> Riesgo:
    """Riesgo en blanco al centro de la matriz: marca que hay algo que mirar."""
    riesgo = Riesgo(project_id=project_id, task_id=task_id, probabilidad=3, impacto=3)
    session.add(riesgo)
    session.commit()
    session.refresh(riesgo)
    return riesgo


def desvincular(session: Session, task_ids: set[int]) -> None:
    """Al borrar tareas: el borrador vacío se va, el riesgo cargado sobrevive suelto.

    Borrar una tarea no debería llevarse en silencio un riesgo que alguien se tomó el
    trabajo de describir; queda como riesgo del proyecto, que es lo que en realidad era.
    """
    if not task_ids:
        return
    for riesgo in session.exec(select(Riesgo).where(Riesgo.task_id.in_(task_ids))):
        if riesgo.descripcion.strip():
            riesgo.task_id = None
            session.add(riesgo)
        else:
            session.delete(riesgo)
    # El plan de mitigación puede apuntar a una tarea que se está borrando: el riesgo
    # queda sin plan enganchado, y el registro lo va a avisar.
    for riesgo in session.exec(select(Riesgo).where(Riesgo.mitigacion_task_id.in_(task_ids))):
        riesgo.mitigacion_task_id = None
        session.add(riesgo)


def eliminar_del_proyecto(session: Session, project_id: int) -> None:
    for riesgo in session.exec(select(Riesgo).where(Riesgo.project_id == project_id)):
        session.delete(riesgo)


def _tarea_del_proyecto(session: Session, project_id: int, task_id: int) -> bool:
    tarea = session.get(Task, task_id)
    return tarea is not None and tarea.project_id == project_id
