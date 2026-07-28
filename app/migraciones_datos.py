"""Migraciones de *datos*, no de esquema. Corren después de `migraciones.poner_al_dia`.

`migraciones.py` agrega columnas y nada más, a propósito. Acá viven los cambios que
además tienen que mover información existente de un lado a otro. Son de una sola vez:
cada una detecta si ya corrió y no hace nada si sí.

Excepción documentada al "solo ORM": leer y borrar una columna que el modelo ya no
declara no se puede expresar con el ORM. Los nombres de tabla y columna son
constantes de este archivo, nunca input del usuario.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, select

from .models import Estado, Project, Task
from .services import estados as estados_service

log = logging.getLogger("wopr.migraciones")

# Los tres valores del viejo enum `EstadoTarea`, en el orden de `ESTADOS_POR_DEFECTO`.
_ESTADOS_V1 = ["pendiente", "en_curso", "hecha"]


def poner_al_dia(engine: Engine) -> list[str]:
    aplicadas: list[str] = []
    with Session(engine) as session:
        aplicadas += _sembrar_estados(session)
    aplicadas += _migrar_estado_a_tabla(engine)
    return aplicadas


def _sembrar_estados(session: Session) -> list[str]:
    """Todo proyecto necesita sus estados; los que vienen de v1 no tienen ninguno."""
    hechas = []
    for proyecto in session.exec(select(Project)):
        if proyecto.id is None:
            continue
        ya_tiene = session.exec(
            select(Estado).where(Estado.project_id == proyecto.id)
        ).first()
        if ya_tiene is None:
            estados_service.asegurar_defaults(session, proyecto.id)
            hechas.append(f"estados sembrados en proyecto {proyecto.id}")
    return hechas


def _migrar_estado_a_tabla(engine: Engine) -> list[str]:
    """Convierte la vieja columna `task.estado` (texto) en un vínculo a `estado`.

    Se hace en dos pasos y en ese orden: primero se traduce cada valor al id del
    estado equivalente del proyecto, y recién después se borra la columna. Si algo
    fallara en el medio, la columna vieja sigue ahí y el dato no se pierde.
    """
    inspector = inspect(engine)
    if "task" not in set(inspector.get_table_names()):
        return []
    if "estado" not in {c["name"] for c in inspector.get_columns("task")}:
        return []  # ya migrada

    with Session(engine) as session:
        por_proyecto: dict[int, list[Estado]] = {}
        for estado in session.exec(select(Estado)):
            por_proyecto.setdefault(estado.project_id, []).append(estado)
        for lista in por_proyecto.values():
            lista.sort(key=lambda e: (e.orden, e.id or 0))

        filas = session.exec(text("SELECT id, project_id, estado FROM task")).all()
        for task_id, project_id, viejo in filas:
            estados = por_proyecto.get(project_id) or []
            if not estados:
                continue
            indice = _ESTADOS_V1.index(viejo) if viejo in _ESTADOS_V1 else 0
            equivalente = estados[min(indice, len(estados) - 1)]
            tarea = session.get(Task, task_id)
            if tarea is not None:
                tarea.estado_id = equivalente.id
                session.add(tarea)
        session.commit()

    with engine.begin() as conexion:
        conexion.execute(text("ALTER TABLE task DROP COLUMN estado"))
    log.info("Columna task.estado migrada a task.estado_id y eliminada")
    return ["task.estado → task.estado_id"]
