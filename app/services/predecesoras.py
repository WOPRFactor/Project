"""Dependencias escritas a mano en la grilla, referenciadas por código.

Se escribe como en Project: `1.3` para una simple, `1.3+2` para esperar dos días
hábiles más, `1.3-1` para solapar uno. Varias van separadas por coma.

La celda es la fuente de verdad: al guardarla, las dependencias de esa tarea
quedan exactamente como dice el texto — las que faltan se crean, las que sobran
se borran.
"""

from __future__ import annotations

import re

from sqlmodel import Session, select

from ..engine import CycleError, ScheduleError
from ..models import Dependency, Task
from . import schedule as schedule_service
from .tasks import TareaInvalida

_REFERENCIA = re.compile(r"^([0-9]+(?:\.[0-9]+)*)\s*([+-]\s*[0-9]{1,3})?$")


def texto_de(session: Session, project_id: int, task_id: int) -> str:
    """Cómo se muestra la celda: los códigos de las predecesoras, con su lag."""
    codigos = {
        t.id: t.codigo
        for t in session.exec(select(Task).where(Task.project_id == project_id))
    }
    partes = []
    for dep in session.exec(
        select(Dependency).where(
            Dependency.project_id == project_id, Dependency.successor_id == task_id
        )
    ):
        codigo = codigos.get(dep.predecessor_id) or str(dep.predecessor_id)
        if dep.lag > 0:
            codigo += f"+{dep.lag}"
        elif dep.lag < 0:
            codigo += str(dep.lag)
        partes.append(codigo)
    return ", ".join(sorted(partes))


def guardar(session: Session, project_id: int, task_id: int, texto: str) -> list[str]:
    """Deja las predecesoras de la tarea igual a lo escrito. Devuelve los avisos."""
    tareas = list(session.exec(select(Task).where(Task.project_id == project_id)))
    por_codigo = {t.codigo: t for t in tareas if t.codigo}
    avisos: list[str] = []

    pedidas: dict[int, int] = {}
    for crudo in texto.replace(";", ",").split(","):
        crudo = crudo.strip()
        if not crudo:
            continue
        referencia = _REFERENCIA.match(crudo)
        if referencia is None:
            avisos.append(f"«{crudo}» no se entiende: se escribe 1.3 o 1.3+2")
            continue
        codigo, lag_crudo = referencia.group(1), referencia.group(2)
        predecesora = por_codigo.get(codigo)
        if predecesora is None:
            avisos.append(f"No existe ninguna tarea con código {codigo}")
            continue
        if predecesora.id == task_id:
            avisos.append("Una tarea no puede depender de sí misma")
            continue
        pedidas[predecesora.id] = int((lag_crudo or "0").replace(" ", ""))

    return _sincronizar(session, project_id, task_id, pedidas, avisos)


def _sincronizar(
    session: Session,
    project_id: int,
    task_id: int,
    pedidas: dict[int, int],
    avisos: list[str],
) -> list[str]:
    actuales = {
        d.predecessor_id: d
        for d in session.exec(
            select(Dependency).where(
                Dependency.project_id == project_id, Dependency.successor_id == task_id
            )
        )
    }

    for predecesora_id, dependencia in actuales.items():
        if predecesora_id not in pedidas:
            session.delete(dependencia)
    session.commit()

    for predecesora_id, lag in pedidas.items():
        existente = actuales.get(predecesora_id)
        if existente is not None and existente.lag == lag:
            continue
        if existente is not None:
            existente.lag = lag
            session.add(existente)
            session.commit()
            continue
        candidata = Dependency(
            project_id=project_id,
            predecessor_id=predecesora_id,
            successor_id=task_id,
            lag=lag,
        )
        aviso = _agregar_si_valida(session, project_id, candidata)
        if aviso:
            avisos.append(aviso)

    return avisos


def _agregar_si_valida(
    session: Session, project_id: int, candidata: Dependency
) -> str | None:
    """Prueba la dependencia contra el motor antes de guardarla."""
    try:
        schedule_service.calcular(session, project_id, extra=[candidata])
    except CycleError:
        return "Esa dependencia crearía un ciclo, no la guardé"
    except ScheduleError as error:
        return str(error)
    session.add(candidata)
    session.commit()
    return None


def borrar_de_tarea(session: Session, project_id: int, task_id: int) -> None:
    for dep in session.exec(
        select(Dependency).where(
            Dependency.project_id == project_id, Dependency.successor_id == task_id
        )
    ):
        session.delete(dep)
    session.commit()


__all__ = ["texto_de", "guardar", "borrar_de_tarea", "TareaInvalida"]
