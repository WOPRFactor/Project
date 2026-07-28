"""Riesgos del proyecto: alta, edición, borrado y armado del cuadrante.

La aritmética de la matriz vive en `matriz.py` y no toca la base. Acá se lee, se
escribe y se le pasa a ese módulo lo que necesita.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from ..models import EstadoRiesgo, Riesgo, Task
from . import matriz as matriz_service


class RiesgoInvalido(Exception):
    """Operación rechazada; el mensaje se le muestra al usuario."""


@dataclass(frozen=True)
class Panel:
    """Todo lo que la pantalla de riesgos necesita, ya calculado."""

    riesgos: list[Riesgo]
    cuadrante: list[list[matriz_service.Celda]]
    por_zona: dict
    titulos: dict[int, str]

    @property
    def abiertos(self) -> int:
        return len([r for r in self.riesgos if r.estado == EstadoRiesgo.abierto])


def listar(session: Session, project_id: int) -> list[Riesgo]:
    riesgos = list(session.exec(select(Riesgo).where(Riesgo.project_id == project_id)))
    # Lo más severo primero: es el orden en que se mira una lista de riesgos.
    riesgos.sort(key=lambda r: (-r.probabilidad * r.impacto, r.id or 0))
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

    riesgo = Riesgo(project_id=project_id, task_id=task_id, **datos.model_dump())
    session.add(riesgo)
    session.commit()
    session.refresh(riesgo)
    return riesgo


def actualizar(session: Session, riesgo_id: int, datos) -> Riesgo:
    riesgo = session.get(Riesgo, riesgo_id)
    if riesgo is None:
        raise RiesgoInvalido("Ese riesgo ya no existe")
    for campo, valor in datos.model_dump().items():
        setattr(riesgo, campo, valor)
    session.add(riesgo)
    session.commit()
    session.refresh(riesgo)
    return riesgo


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


def panel(session: Session, project_id: int) -> Panel:
    riesgos = listar(session, project_id)
    # Un riesgo cerrado ya no ocupa lugar en el cuadrante: ensuciaría la lectura.
    vivos = [
        (r.id or 0, r.probabilidad, r.impacto)
        for r in riesgos
        if r.estado != EstadoRiesgo.cerrado
    ]
    titulos = {
        t.id: t.titulo
        for t in session.exec(select(Task).where(Task.project_id == project_id))
        if t.id is not None
    }
    return Panel(
        riesgos=riesgos,
        cuadrante=matriz_service.cuadrante(vivos),
        por_zona=matriz_service.por_zona(vivos),
        titulos=titulos,
    )


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


def eliminar_del_proyecto(session: Session, project_id: int) -> None:
    for riesgo in session.exec(select(Riesgo).where(Riesgo.project_id == project_id)):
        session.delete(riesgo)


def _tarea_del_proyecto(session: Session, project_id: int, task_id: int) -> bool:
    tarea = session.get(Task, task_id)
    return tarea is not None and tarea.project_id == project_id
