"""Árbol de tareas: alta, edición, movimiento y borrado.

Invariante que se cuida acá: el árbol nunca queda inconsistente. Una tarea no puede
colgar de sí misma ni de una descendiente suya.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import Dependency, Task
from ..schemas import TareaIn
from . import estados as estados_service
from . import riesgos as riesgos_service


class TareaInvalida(Exception):
    """Operación rechazada sobre el árbol; el mensaje se muestra al usuario."""


def listar(session: Session, project_id: int) -> list[Task]:
    return list(session.exec(select(Task).where(Task.project_id == project_id)))


def obtener(session: Session, task_id: int) -> Task | None:
    return session.get(Task, task_id)


def arbol(session: Session, project_id: int) -> list[tuple[Task, int]]:
    """Tareas en orden de recorrido del árbol, con su nivel de indentación."""
    tareas = listar(session, project_id)
    hijas: dict[int | None, list[Task]] = {}
    for tarea in tareas:
        hijas.setdefault(tarea.parent_id, []).append(tarea)
    for grupo in hijas.values():
        grupo.sort(key=lambda t: (t.orden, t.id or 0))

    salida: list[tuple[Task, int]] = []

    def bajar(padre: int | None, nivel: int) -> None:
        for tarea in hijas.get(padre, []):
            salida.append((tarea, nivel))
            bajar(tarea.id, nivel + 1)

    bajar(None, 0)
    return salida


def tiene_hijas(session: Session, task_id: int) -> bool:
    return bool(session.exec(select(Task).where(Task.parent_id == task_id)).first())


def ids_descendientes(session: Session, project_id: int, task_id: int) -> set[int]:
    tareas = listar(session, project_id)
    hijas: dict[int | None, list[int]] = {}
    for tarea in tareas:
        hijas.setdefault(tarea.parent_id, []).append(tarea.id or 0)

    encontrados: set[int] = set()
    pila = list(hijas.get(task_id, []))
    while pila:
        actual = pila.pop()
        if actual in encontrados:
            continue
        encontrados.add(actual)
        pila.extend(hijas.get(actual, []))
    return encontrados


def crear(session: Session, project_id: int, datos: TareaIn) -> Task:
    if datos.parent_id is not None:
        padre = session.get(Task, datos.parent_id)
        if padre is None or padre.project_id != project_id:
            raise TareaInvalida("La tarea padre no existe en este proyecto")

    ultimo = max(
        (t.orden for t in listar(session, project_id) if t.parent_id == datos.parent_id),
        default=-1,
    )
    tarea = Task(project_id=project_id, orden=ultimo + 1, **datos.model_dump())
    tarea.estado_id = _estado_valido(session, project_id, datos.estado_id)
    session.add(tarea)
    session.commit()
    session.refresh(tarea)
    return tarea


def actualizar(session: Session, task_id: int, datos: TareaIn) -> Task | None:
    tarea = session.get(Task, task_id)
    if tarea is None:
        return None
    valores = datos.model_dump(exclude={"parent_id", "estado_id"})
    for campo, valor in valores.items():
        setattr(tarea, campo, valor)
    tarea.estado_id = _estado_valido(
        session, tarea.project_id, datos.estado_id or tarea.estado_id
    )
    session.add(tarea)
    session.commit()
    session.refresh(tarea)
    return tarea


def mover(session: Session, task_id: int, nuevo_padre_id: int | None) -> Task:
    tarea = session.get(Task, task_id)
    if tarea is None:
        raise TareaInvalida("La tarea no existe")
    if nuevo_padre_id == task_id:
        raise TareaInvalida("Una tarea no puede colgar de sí misma")

    if nuevo_padre_id is not None:
        padre = session.get(Task, nuevo_padre_id)
        if padre is None or padre.project_id != tarea.project_id:
            raise TareaInvalida("La tarea padre no existe en este proyecto")
        if nuevo_padre_id in ids_descendientes(session, tarea.project_id, task_id):
            raise TareaInvalida("No podés colgar una tarea de una de sus subtareas")

    tarea.parent_id = nuevo_padre_id
    session.add(tarea)
    session.commit()
    session.refresh(tarea)
    return tarea


def cambiar_estado(session: Session, task_id: int, estado_id: int | None) -> Task | None:
    tarea = session.get(Task, task_id)
    if tarea is None:
        return None
    tarea.estado_id = _estado_valido(session, tarea.project_id, estado_id)
    session.add(tarea)
    session.commit()
    session.refresh(tarea)
    return tarea


def _estado_valido(session: Session, project_id: int, estado_id: int | None) -> int | None:
    """Un id de estado solo vale si es de este proyecto; si no, cae en el inicial.

    El id llega de un formulario, así que no se toma como viene: un estado de otro
    proyecto mezclaría vocabularios y rompería el conteo de avance.
    """
    if estado_id is not None:
        estado = estados_service.obtener(session, estado_id)
        if estado is not None and estado.project_id == project_id:
            return estado.id
    return estados_service.inicial(session, project_id).id


def eliminar(session: Session, task_id: int, promover_hijas: bool = False) -> bool:
    """Borra la tarea. Sus hijas se borran también, salvo que se pidan promover."""
    tarea = session.get(Task, task_id)
    if tarea is None:
        return False

    if promover_hijas:
        for hija in session.exec(select(Task).where(Task.parent_id == task_id)):
            hija.parent_id = tarea.parent_id
            session.add(hija)
        a_borrar = {task_id}
    else:
        a_borrar = {task_id} | ids_descendientes(session, tarea.project_id, task_id)

    for dep in session.exec(select(Dependency).where(Dependency.project_id == tarea.project_id)):
        if dep.predecessor_id in a_borrar or dep.successor_id in a_borrar:
            session.delete(dep)
    riesgos_service.desvincular(session, a_borrar)
    for identificador in a_borrar:
        objetivo = session.get(Task, identificador)
        if objetivo is not None:
            session.delete(objetivo)
    session.commit()
    return True
