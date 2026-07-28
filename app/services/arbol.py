"""Operaciones de fila sobre el árbol: insertar, indentar, desindentar, renumerar.

Son los movimientos que uno espera de una grilla tipo Project: agregar una fila
debajo, correrla un nivel a la derecha para que sea subtarea, o traerla de vuelta.
El orden entre hermanas se mantiene compacto (0, 1, 2…) después de cada cambio.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import Task
from ..schemas import TareaIn
from .tasks import TareaInvalida, ids_descendientes


def hermanas(session: Session, project_id: int, parent_id: int | None) -> list[Task]:
    tareas = session.exec(
        select(Task).where(Task.project_id == project_id, Task.parent_id == parent_id)
    ).all()
    return sorted(tareas, key=lambda t: (t.orden, t.id or 0))


def codigo_sugerido(session: Session, project_id: int, parent_id: int | None) -> str:
    """Siguiente código libre: 3 si cuelga de la raíz, 2.4 si cuelga de 2.

    La unicidad se chequea contra **todo el proyecto**, no solo entre hermanas: si el
    padre no tiene código, el prefijo queda vacío y un conteo local generaría un
    duplicado de algún código de primer nivel — y con códigos repetidos las
    dependencias escritas a mano apuntarían a cualquier lado.
    """
    prefijo = ""
    if parent_id is not None:
        padre = session.get(Task, parent_id)
        prefijo = (padre.codigo + ".") if padre and padre.codigo else ""

    ocupados = {
        t.codigo
        for t in session.exec(select(Task).where(Task.project_id == project_id))
        if t.codigo
    }
    siguiente = 1
    while f"{prefijo}{siguiente}" in ocupados:
        siguiente += 1
    return f"{prefijo}{siguiente}"


def insertar_debajo(session: Session, task_id: int) -> Task:
    """Fila nueva y vacía justo debajo de la actual, al mismo nivel."""
    referencia = session.get(Task, task_id)
    if referencia is None:
        raise TareaInvalida("La tarea no existe")

    for hermana in hermanas(session, referencia.project_id, referencia.parent_id):
        if hermana.orden > referencia.orden:
            hermana.orden += 1
            session.add(hermana)

    nueva = Task(
        project_id=referencia.project_id,
        parent_id=referencia.parent_id,
        titulo="Tarea nueva",
        duracion=1,
        orden=referencia.orden + 1,
        codigo="",
    )
    session.add(nueva)
    session.commit()
    session.refresh(nueva)

    nueva.codigo = codigo_sugerido(session, referencia.project_id, referencia.parent_id)
    session.add(nueva)
    session.commit()
    session.refresh(nueva)
    _compactar(session, referencia.project_id, referencia.parent_id)
    return nueva


def agregar_al_final(session: Session, project_id: int, datos: TareaIn) -> Task:
    """Alta normal, pero asignando el código que corresponde al nivel."""
    from . import tasks as tasks_service

    tarea = tasks_service.crear(session, project_id, datos)
    if not tarea.codigo:
        tarea.codigo = codigo_sugerido(session, project_id, tarea.parent_id)
        session.add(tarea)
        session.commit()
        session.refresh(tarea)
    return tarea


def indentar(session: Session, task_id: int) -> Task:
    """La tarea pasa a ser hija de la hermana que tiene arriba."""
    tarea = session.get(Task, task_id)
    if tarea is None:
        raise TareaInvalida("La tarea no existe")

    grupo = hermanas(session, tarea.project_id, tarea.parent_id)
    posicion = [h.id for h in grupo].index(tarea.id)
    if posicion == 0:
        raise TareaInvalida("No hay una tarea arriba de la que colgarla")

    nuevo_padre = grupo[posicion - 1]
    tarea.parent_id = nuevo_padre.id
    tarea.orden = len(hermanas(session, tarea.project_id, nuevo_padre.id))
    tarea.codigo = ""
    session.add(tarea)
    session.commit()
    session.refresh(tarea)

    tarea.codigo = codigo_sugerido(session, tarea.project_id, nuevo_padre.id)
    session.add(tarea)
    session.commit()
    session.refresh(tarea)
    return tarea


def desindentar(session: Session, task_id: int) -> Task:
    """La tarea sube un nivel y queda justo después de su ex-padre."""
    tarea = session.get(Task, task_id)
    if tarea is None:
        raise TareaInvalida("La tarea no existe")
    if tarea.parent_id is None:
        raise TareaInvalida("La tarea ya está en el primer nivel")

    padre = session.get(Task, tarea.parent_id)
    abuelo_id = padre.parent_id

    for hermana in hermanas(session, tarea.project_id, abuelo_id):
        if hermana.orden > padre.orden:
            hermana.orden += 1
            session.add(hermana)

    tarea.parent_id = abuelo_id
    tarea.orden = padre.orden + 1
    tarea.codigo = ""
    session.add(tarea)
    session.commit()
    session.refresh(tarea)

    tarea.codigo = codigo_sugerido(session, tarea.project_id, abuelo_id)
    session.add(tarea)
    session.commit()
    session.refresh(tarea)
    _compactar(session, tarea.project_id, abuelo_id)
    return tarea


def renumerar(session: Session, project_id: int) -> int:
    """Reasigna todos los códigos según la posición actual en el árbol.

    Rompe a propósito las referencias escritas a mano que ya no correspondan: por
    eso es una acción explícita del usuario y no algo automático.
    """
    from . import tasks as tasks_service

    cambiados = 0

    def bajar(parent_id: int | None, prefijo: str) -> None:
        nonlocal cambiados
        for indice, tarea in enumerate(hermanas(session, project_id, parent_id), start=1):
            nuevo = f"{prefijo}{indice}"
            if tarea.codigo != nuevo:
                tarea.codigo = nuevo
                session.add(tarea)
                cambiados += 1
            bajar(tarea.id, f"{nuevo}.")

    bajar(None, "")
    session.commit()
    tasks_service.listar(session, project_id)
    return cambiados


def _compactar(session: Session, project_id: int, parent_id: int | None) -> None:
    for indice, hermana in enumerate(hermanas(session, project_id, parent_id)):
        if hermana.orden != indice:
            hermana.orden = indice
            session.add(hermana)
    session.commit()


__all__ = [
    "agregar_al_final",
    "codigo_sugerido",
    "desindentar",
    "hermanas",
    "indentar",
    "insertar_debajo",
    "renumerar",
    "ids_descendientes",
]
