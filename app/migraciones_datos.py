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

from .models import Contacto, Estado, Project, Riesgo, Task
from .services import contactos as contactos_service
from .services import estados as estados_service

log = logging.getLogger("wopr.migraciones")

# Los tres valores del viejo enum `EstadoTarea`, en el orden de `ESTADOS_POR_DEFECTO`.
_ESTADOS_V1 = ["pendiente", "en_curso", "hecha"]


def poner_al_dia(engine: Engine, agregadas: list[str] | None = None) -> list[str]:
    """`agregadas` son las columnas que acaba de crear `migraciones.poner_al_dia`.

    Se usa para correr una migración de datos **exactamente una vez**: cuando la
    columna nació recién. Adivinarlo mirando los datos sería frágil.
    """
    aplicadas: list[str] = []
    with Session(engine) as session:
        aplicadas += _sembrar_estados(session)
    aplicadas += _migrar_estado_a_tabla(engine)
    aplicadas += _migrar_responsable_a_contacto(engine)
    if "task.avance" in (agregadas or []):
        with Session(engine) as session:
            aplicadas += _avance_desde_estado(session)
    return aplicadas


def _avance_desde_estado(session: Session) -> list[str]:
    """El avance nace del estado que ya tenía cada tarea.

    Sin esto, una tarea marcada «Hecha» en la versión anterior aparecería al 0% y el
    proyecto entero mostraría un retroceso que nunca pasó.
    """
    estados = {e.id: e for e in session.exec(select(Estado))}
    tocadas = 0
    for tarea in session.exec(select(Task)):
        estado = estados.get(tarea.estado_id or 0)
        if estado is not None and tarea.avance != estado.avance_sugerido:
            tarea.avance = estado.avance_sugerido
            session.add(tarea)
            tocadas += 1
    session.commit()
    return [f"avance sembrado desde el estado en {tocadas} tareas"] if tocadas else []


def _migrar_responsable_a_contacto(engine: Engine) -> list[str]:
    """Convierte los viejos `responsable` de texto en contactos del proyecto.

    Deduplica por nombre normalizado, así los «Ariel» / «ariel» de una planilla
    entran como una sola persona. Igual que con los estados: primero se traduce y
    recién después se borra la columna, para que un fallo en el medio no pierda nada.
    """
    return _texto_a_contacto(engine, "task", Task) + _texto_a_contacto(
        engine, "riesgo", Riesgo
    )


def _texto_a_contacto(engine: Engine, tabla: str, modelo) -> list[str]:
    inspector = inspect(engine)
    if tabla not in set(inspector.get_table_names()):
        return []
    if "responsable" not in {c["name"] for c in inspector.get_columns(tabla)}:
        return []  # ya migrada

    with Session(engine) as session:
        filas = session.exec(
            text(f"SELECT id, project_id, responsable FROM {tabla}")  # noqa: S608
        ).all()
        creados = 0
        for fila_id, project_id, nombre in filas:
            if not (nombre or "").strip():
                continue
            antes = len(contactos_service.listar(session, project_id))
            contacto_id = contactos_service.resolver(session, project_id, nombre)
            creados += len(contactos_service.listar(session, project_id)) - antes
            registro = session.get(modelo, fila_id)
            if registro is not None:
                registro.responsable_id = contacto_id
                session.add(registro)
        session.commit()

    with engine.begin() as conexion:
        conexion.execute(text(f"ALTER TABLE {tabla} DROP COLUMN responsable"))
    log.info("Columna %s.responsable migrada a contactos (%s creados)", tabla, creados)
    return [f"{tabla}.responsable → contacto ({creados} personas)"]


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
