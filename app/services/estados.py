"""Estados de tarea definidos por el usuario, por proyecto.

Antes eran un enum de tres valores clavado en el código y la app preguntaba
`estado == "hecha"` en media docena de archivos. Ahora los define el usuario, y el
único dato que el motor necesita de ellos es `es_final`.

Regla que se cuida acá: **un proyecto nunca se queda sin estados y nunca sin un
estado final.** Si eso pasara, ninguna tarea podría darse por terminada y el avance
quedaría clavado en 0 sin explicación.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import ESTADOS_POR_DEFECTO, Estado, Task


class EstadoInvalido(Exception):
    """Operación rechazada sobre los estados; el mensaje se le muestra al usuario."""


def listar(session: Session, project_id: int) -> list[Estado]:
    estados = list(session.exec(select(Estado).where(Estado.project_id == project_id)))
    estados.sort(key=lambda e: (e.orden, e.id or 0))
    return estados


def obtener(session: Session, estado_id: int) -> Estado | None:
    return session.get(Estado, estado_id)


def asegurar_defaults(session: Session, project_id: int) -> list[Estado]:
    """Siembra los tres estados iniciales si el proyecto todavía no tiene ninguno."""
    existentes = listar(session, project_id)
    if existentes:
        return existentes

    for orden, (nombre, color, es_final, avance) in enumerate(ESTADOS_POR_DEFECTO):
        session.add(Estado(
            project_id=project_id, nombre=nombre, color=color,
            orden=orden, es_final=es_final, avance_sugerido=avance,
        ))
    session.commit()
    return listar(session, project_id)


def inicial(session: Session, project_id: int) -> Estado:
    """El estado con el que nace una tarea: el primero del orden."""
    return asegurar_defaults(session, project_id)[0]


def final(session: Session, project_id: int) -> Estado | None:
    """El primer estado terminal. Es lo que la app usa para «esto ya está»."""
    return next((e for e in listar(session, project_id) if e.es_final), None)


def crear(
    session: Session, project_id: int, nombre: str, color, es_final: bool, avance: int
) -> Estado:
    estados = listar(session, project_id)
    estado = Estado(
        project_id=project_id,
        nombre=nombre,
        color=color,
        orden=max((e.orden for e in estados), default=-1) + 1,
        es_final=es_final,
        avance_sugerido=avance,
    )
    session.add(estado)
    session.commit()
    session.refresh(estado)
    return estado


def actualizar(
    session: Session, estado_id: int, nombre: str, color, es_final: bool, avance: int
) -> Estado:
    estado = session.get(Estado, estado_id)
    if estado is None:
        raise EstadoInvalido("Ese estado ya no existe")
    if estado.es_final and not es_final and not _otro_final(session, estado):
        raise EstadoInvalido(
            "Es el único estado final del proyecto: sin él ninguna tarea podría darse "
            "por terminada. Marcá otro como final antes de sacarle la marca a este."
        )

    estado.nombre, estado.color = nombre, color
    estado.es_final, estado.avance_sugerido = es_final, avance
    session.add(estado)
    session.commit()
    session.refresh(estado)
    return estado


def eliminar(session: Session, estado_id: int, reemplazo_id: int | None = None) -> None:
    """Borra un estado reasignando sus tareas. No se borra sin destino."""
    estado = session.get(Estado, estado_id)
    if estado is None:
        return

    restantes = [e for e in listar(session, estado.project_id) if e.id != estado_id]
    if not restantes:
        raise EstadoInvalido("Es el único estado del proyecto; no se puede borrar")
    if estado.es_final and not any(e.es_final for e in restantes):
        raise EstadoInvalido(
            "Es el único estado final: marcá otro como final antes de borrarlo"
        )

    destino = session.get(Estado, reemplazo_id) if reemplazo_id else None
    if destino is None or destino.project_id != estado.project_id or destino.id == estado_id:
        destino = restantes[0]

    for tarea in session.exec(select(Task).where(Task.estado_id == estado_id)):
        tarea.estado_id = destino.id
        session.add(tarea)
    session.delete(estado)
    session.commit()


def mapa(session: Session, project_id: int) -> dict[int, Estado]:
    return {e.id: e for e in listar(session, project_id) if e.id is not None}


def _otro_final(session: Session, estado: Estado) -> bool:
    return any(
        e.es_final for e in listar(session, estado.project_id) if e.id != estado.id
    )
