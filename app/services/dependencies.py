"""Dependencias Fin→Inicio con lag.

Antes de guardar, la dependencia candidata se prueba contra el motor: si genera un
ciclo o toca una tarea resumen, se rechaza con el mensaje del motor y no se persiste.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..engine import CycleError, ScheduleError
from ..models import Dependency, Task
from ..schemas import DependenciaIn
from . import schedule as schedule_service
from .tasks import TareaInvalida


def listar(session: Session, project_id: int) -> list[Dependency]:
    return list(session.exec(select(Dependency).where(Dependency.project_id == project_id)))


def por_sucesora(session: Session, project_id: int) -> dict[int, list[Dependency]]:
    agrupadas: dict[int, list[Dependency]] = {}
    for dep in listar(session, project_id):
        agrupadas.setdefault(dep.successor_id, []).append(dep)
    return agrupadas


def crear(session: Session, project_id: int, datos: DependenciaIn) -> Dependency:
    """Valida contra el motor y persiste. Lanza TareaInvalida con mensaje mostrable."""
    for extremo in (datos.predecessor_id, datos.successor_id):
        tarea = session.get(Task, extremo)
        if tarea is None or tarea.project_id != project_id:
            raise TareaInvalida("Alguna de las tareas no existe en este proyecto")

    ya_existe = session.exec(
        select(Dependency).where(
            Dependency.project_id == project_id,
            Dependency.predecessor_id == datos.predecessor_id,
            Dependency.successor_id == datos.successor_id,
        )
    ).first()
    if ya_existe is not None:
        raise TareaInvalida("Esa dependencia ya existe")

    candidata = Dependency(project_id=project_id, **datos.model_dump())
    try:
        schedule_service.calcular(session, project_id, extra=[candidata])
    except CycleError as error:
        raise TareaInvalida(_ciclo_con_titulos(session, error)) from error
    except ScheduleError as error:
        raise TareaInvalida(str(error)) from error

    session.add(candidata)
    session.commit()
    session.refresh(candidata)
    return candidata


def _ciclo_con_titulos(session: Session, error: CycleError) -> str:
    """El motor razona con ids; el usuario lee títulos."""
    titulos = []
    for task_id in error.ciclo:
        tarea = session.get(Task, task_id)
        titulos.append(f"«{tarea.titulo}»" if tarea else f"tarea {task_id}")
    return "Esa dependencia crea un ciclo: " + " → ".join(titulos)


def eliminar(session: Session, dependency_id: int) -> bool:
    dependencia = session.get(Dependency, dependency_id)
    if dependencia is None:
        return False
    session.delete(dependencia)
    session.commit()
    return True
