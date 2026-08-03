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

from .models import Contacto, Estado, Project, Task
from .services import contactos as contactos_service
from .services import estados as estados_service

log = logging.getLogger("wopr.migraciones")

# Los tres valores del viejo enum `EstadoTarea`, en el orden de `ESTADOS_POR_DEFECTO`.
_ESTADOS_V1 = ["pendiente", "en_curso", "hecha"]

_TABLA_REGISTRO = "migracion_aplicada"
_SIEMBRA_AVANCE = "avance_desde_estado"


def preparar_registro(engine: Engine) -> None:
    """Crea la tabla que anota qué migraciones de datos ya corrieron.

    Va **antes** de tocar el esquema: si el proceso muere entre el ALTER y la
    migración de datos, en el próximo arranque la ausencia de la marca dice que
    falta correr — una señal en memoria se pierde con el proceso. Si la tabla nace
    sobre una base que ya tiene `task.avance`, esa base migró con el código viejo:
    se anota sin correr nada, para no pisar avances que el usuario ya editó.
    """
    inspector = inspect(engine)
    tablas = set(inspector.get_table_names())
    if _TABLA_REGISTRO in tablas:
        return
    ya_migrada = "task" in tablas and "avance" in {
        c["name"] for c in inspector.get_columns("task")
    }
    with engine.begin() as conexion:
        conexion.execute(
            text(f'CREATE TABLE "{_TABLA_REGISTRO}" (nombre TEXT PRIMARY KEY)')
        )
        if ya_migrada:
            conexion.execute(
                text(f'INSERT INTO "{_TABLA_REGISTRO}" (nombre) VALUES (:n)'),
                {"n": _SIEMBRA_AVANCE},
            )


def poner_al_dia(engine: Engine) -> list[str]:
    """Corre las migraciones de datos pendientes. Cada una detecta **en la base**
    si ya corrió: por la columna vieja que sigue existiendo, o por su marca en
    `migracion_aplicada`."""
    preparar_registro(engine)
    aplicadas: list[str] = []
    with Session(engine) as session:
        aplicadas += _sembrar_estados(session)
    aplicadas += _migrar_estado_a_tabla(engine)
    aplicadas += _migrar_responsable_a_contacto(engine)
    if not _corrida(engine, _SIEMBRA_AVANCE):
        with Session(engine) as session:
            aplicadas += _avance_desde_estado(session)
    with Session(engine) as session:
        aplicadas += adoptar_proyectos_sin_duenio(session)
    return aplicadas


def adoptar_proyectos_sin_duenio(session: Session) -> list[str]:
    """Todo proyecto necesita dueño; los de la etapa monousuario no tienen ninguno.

    Se le asignan al primer admin. Corre en cada arranque a propósito: un
    proyecto puede quedar sin dueño si se borra la cuenta que lo era, y esta es
    la red que evita que se vuelva inalcanzable. Sin ningún admin todavía (base
    recién creada, antes del primer usuario) no hace nada y se reintenta después.
    """
    from .models_auth import Miembro, Rol, Usuario

    admin = session.exec(
        select(Usuario).where(Usuario.es_admin == True, Usuario.activo == True)  # noqa: E712
    ).first()
    if admin is None:
        return []

    con_duenio = {
        m.project_id
        for m in session.exec(select(Miembro).where(Miembro.rol == Rol.duenio))
    }
    adoptados = 0
    for proyecto in session.exec(select(Project)):
        if proyecto.id in con_duenio:
            continue
        session.add(
            Miembro(project_id=proyecto.id or 0, usuario_id=admin.id or 0, rol=Rol.duenio)
        )
        adoptados += 1
    if adoptados:
        session.commit()
        log.info("%s proyectos sin dueño adoptados por %s", adoptados, admin.mail)
    return [f"{adoptados} proyectos adoptados por {admin.mail}"] if adoptados else []


def _corrida(engine: Engine, nombre: str) -> bool:
    with engine.connect() as conexion:
        fila = conexion.execute(
            text(f'SELECT nombre FROM "{_TABLA_REGISTRO}" WHERE nombre = :n'),
            {"n": nombre},
        ).first()
    return fila is not None


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
    # La marca va en la misma transacción que la siembra: o pasan las dos o ninguna.
    session.connection().execute(
        text(f'INSERT OR IGNORE INTO "{_TABLA_REGISTRO}" (nombre) VALUES (:n)'),
        {"n": _SIEMBRA_AVANCE},
    )
    session.commit()
    return [f"avance sembrado desde el estado en {tocadas} tareas"] if tocadas else []


def _migrar_responsable_a_contacto(engine: Engine) -> list[str]:
    """Convierte el viejo `task.responsable` (texto) en contactos del proyecto.

    Deduplica por nombre normalizado, así los «Ariel» / «ariel» de una planilla
    entran como una sola persona. Igual que con los estados: primero se traduce y
    recién después se borra la columna, para que un fallo en el medio no pierda nada.
    """
    inspector = inspect(engine)
    if "task" not in set(inspector.get_table_names()):
        return []
    if "responsable" not in {c["name"] for c in inspector.get_columns("task")}:
        return []  # ya migrada

    with Session(engine) as session:
        filas = session.exec(text("SELECT id, project_id, responsable FROM task")).all()
        creados = 0
        for task_id, project_id, nombre in filas:
            if not (nombre or "").strip():
                continue
            antes = len(contactos_service.listar(session, project_id))
            contacto_id = contactos_service.resolver(session, project_id, nombre)
            creados += len(contactos_service.listar(session, project_id)) - antes
            tarea = session.get(Task, task_id)
            if tarea is not None:
                tarea.responsable_id = contacto_id
                session.add(tarea)
        session.commit()

    with engine.begin() as conexion:
        conexion.execute(text("ALTER TABLE task DROP COLUMN responsable"))
    log.info("Columna task.responsable migrada a contactos (%s creados)", creados)
    return [f"task.responsable → contacto ({creados} personas)"]


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

    sin_traducir = 0
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
                sin_traducir += 1
                continue
            indice = _ESTADOS_V1.index(viejo) if viejo in _ESTADOS_V1 else 0
            equivalente = estados[min(indice, len(estados) - 1)]
            tarea = session.get(Task, task_id)
            if tarea is not None:
                tarea.estado_id = equivalente.id
                session.add(tarea)
        session.commit()

    if sin_traducir:
        # Tareas de proyectos sin estados (huérfanas de un proyecto borrado): su
        # estado viejo se pierde con el DROP, que al menos quede dicho en el log.
        log.warning(
            "%s tareas sin estados en su proyecto: el valor viejo de `estado` se pierde",
            sin_traducir,
        )
    with engine.begin() as conexion:
        conexion.execute(text("ALTER TABLE task DROP COLUMN estado"))
    log.info("Columna task.estado migrada a task.estado_id y eliminada")
    return ["task.estado → task.estado_id"]
