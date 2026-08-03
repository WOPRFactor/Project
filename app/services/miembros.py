"""Quién participa de cada proyecto y con qué rol (Fase 11).

Dos invariantes que se cuidan acá y que valen más que cualquier pantalla:

- **Un proyecto nunca queda sin dueño.** No se puede sacar ni degradar al
  último; para irte, primero transferís.
- **Borrar un usuario no borra sus proyectos.** Sus membresías se van, el
  proyecto queda — con otro dueño si hacía falta.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import Project
from ..models_auth import Miembro, Rol, Usuario


class MiembroInvalido(Exception):
    """Operación rechazada; el mensaje se le muestra al usuario."""


def rol_de(session: Session, project_id: int, usuario_id: int) -> Rol | None:
    """El rol de alguien en un proyecto, o None si no es miembro."""
    miembro = session.exec(
        select(Miembro).where(
            Miembro.project_id == project_id, Miembro.usuario_id == usuario_id
        )
    ).first()
    return miembro.rol if miembro is not None else None


def listar(session: Session, project_id: int) -> list[tuple[Miembro, Usuario]]:
    """Los miembros con su cuenta, dueños primero y después por mail."""
    filas = [
        (m, session.get(Usuario, m.usuario_id))
        for m in session.exec(select(Miembro).where(Miembro.project_id == project_id))
    ]
    vivos = [(m, u) for m, u in filas if u is not None]
    orden = {Rol.duenio: 0, Rol.editor: 1, Rol.lector: 2}
    vivos.sort(key=lambda par: (orden[par[0].rol], par[1].mail))
    return vivos


def proyectos_de(session: Session, usuario: Usuario) -> list[int]:
    """Los ids de proyecto que este usuario puede ver.

    Un admin ve todo — es el rol que administra la instancia. El resto, solo
    aquello de lo que es miembro.
    """
    if usuario.es_admin:
        return [p.id or 0 for p in session.exec(select(Project))]
    return [
        m.project_id
        for m in session.exec(
            select(Miembro).where(Miembro.usuario_id == usuario.id)
        )
    ]


def agregar(
    session: Session, project_id: int, usuario_id: int, rol: Rol = Rol.editor
) -> Miembro:
    """Suma a alguien al proyecto. Si ya estaba, le cambia el rol."""
    if session.get(Usuario, usuario_id) is None:
        raise MiembroInvalido("Esa cuenta no existe")

    existente = session.exec(
        select(Miembro).where(
            Miembro.project_id == project_id, Miembro.usuario_id == usuario_id
        )
    ).first()
    if existente is not None:
        return cambiar_rol(session, project_id, usuario_id, rol)

    miembro = Miembro(project_id=project_id, usuario_id=usuario_id, rol=rol)
    session.add(miembro)
    session.commit()
    session.refresh(miembro)
    return miembro


def cambiar_rol(
    session: Session, project_id: int, usuario_id: int, rol: Rol
) -> Miembro:
    miembro = session.exec(
        select(Miembro).where(
            Miembro.project_id == project_id, Miembro.usuario_id == usuario_id
        )
    ).first()
    if miembro is None:
        raise MiembroInvalido("Esa persona no es miembro del proyecto")
    if miembro.rol is Rol.duenio and rol is not Rol.duenio and _duenios(session, project_id) <= 1:
        raise MiembroInvalido(
            "Es el último dueño del proyecto: nombrá otro antes de cambiarle el rol"
        )

    miembro.rol = rol
    session.add(miembro)
    session.commit()
    session.refresh(miembro)
    return miembro


def quitar(session: Session, project_id: int, usuario_id: int) -> None:
    miembro = session.exec(
        select(Miembro).where(
            Miembro.project_id == project_id, Miembro.usuario_id == usuario_id
        )
    ).first()
    if miembro is None:
        raise MiembroInvalido("Esa persona no es miembro del proyecto")
    if miembro.rol is Rol.duenio and _duenios(session, project_id) <= 1:
        raise MiembroInvalido(
            "Es el último dueño del proyecto: transferí la propiedad antes de sacarlo"
        )
    session.delete(miembro)
    session.commit()


def quitar_de_todos(session: Session, usuario_id: int) -> None:
    """Al borrar una cuenta. Los proyectos donde era único dueño no quedan
    huérfanos: pasan al admin que ejecuta la baja (lo resuelve el llamador)."""
    for miembro in session.exec(select(Miembro).where(Miembro.usuario_id == usuario_id)):
        session.delete(miembro)
    session.commit()


def eliminar_del_proyecto(session: Session, project_id: int) -> None:
    for miembro in session.exec(select(Miembro).where(Miembro.project_id == project_id)):
        session.delete(miembro)


def _duenios(session: Session, project_id: int) -> int:
    return len([
        m
        for m in session.exec(select(Miembro).where(Miembro.project_id == project_id))
        if m.rol is Rol.duenio
    ])
