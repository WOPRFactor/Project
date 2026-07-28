"""Lógica de negocio de proyectos. Sin FastAPI, sin templates: se testea con una Session."""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import Dependency, Estado, EstadoProyecto, Project, Task
from ..schemas import ProyectoIn
from . import contactos as contactos_service
from . import estados as estados_service
from . import linea_base as linea_base_service
from . import riesgos as riesgos_service


def listar(session: Session, incluir_archivados: bool = False) -> list[Project]:
    consulta = select(Project)
    if not incluir_archivados:
        consulta = consulta.where(Project.estado != EstadoProyecto.archivado)
    proyectos = session.exec(consulta).all()
    orden = {EstadoProyecto.activo: 0, EstadoProyecto.pausado: 1, EstadoProyecto.archivado: 2}
    return sorted(proyectos, key=lambda p: (orden[p.estado], p.nombre.lower()))


def obtener(session: Session, project_id: int) -> Project | None:
    return session.get(Project, project_id)


def crear(session: Session, datos: ProyectoIn) -> Project:
    proyecto = Project(**datos.model_dump())
    session.add(proyecto)
    session.commit()
    session.refresh(proyecto)
    estados_service.asegurar_defaults(session, proyecto.id or 0)
    return proyecto


def actualizar(session: Session, project_id: int, datos: ProyectoIn) -> Project | None:
    proyecto = session.get(Project, project_id)
    if proyecto is None:
        return None
    for campo, valor in datos.model_dump().items():
        setattr(proyecto, campo, valor)
    session.add(proyecto)
    session.commit()
    session.refresh(proyecto)
    return proyecto


def cambiar_estado(
    session: Session, project_id: int, estado: EstadoProyecto
) -> Project | None:
    proyecto = session.get(Project, project_id)
    if proyecto is None:
        return None
    proyecto.estado = estado
    session.add(proyecto)
    session.commit()
    session.refresh(proyecto)
    return proyecto


def eliminar(session: Session, project_id: int) -> bool:
    """Borra el proyecto con todas sus tareas y dependencias."""
    proyecto = session.get(Project, project_id)
    if proyecto is None:
        return False
    for dep in session.exec(select(Dependency).where(Dependency.project_id == project_id)):
        session.delete(dep)
    for tarea in session.exec(select(Task).where(Task.project_id == project_id)):
        session.delete(tarea)
    for estado in session.exec(select(Estado).where(Estado.project_id == project_id)):
        session.delete(estado)
    riesgos_service.eliminar_del_proyecto(session, project_id)
    linea_base_service.eliminar_del_proyecto(session, project_id)
    contactos_service.eliminar_del_proyecto(session, project_id)
    session.delete(proyecto)
    session.commit()
    return True
