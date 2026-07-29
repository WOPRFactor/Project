"""Dependencias escritas a mano en la grilla, referenciadas por código.

Se escribe como en Project: `1.3` para Fin→Inicio, `1.3SS` para que arranquen
juntas, `1.3FF` para que terminen juntas. El lag va pegado: `1.3+2` espera dos
días hábiles, `1.3SS-1` arranca uno antes. Varias, separadas por coma.

La celda es la fuente de verdad: al guardarla, las dependencias de esa tarea
quedan exactamente como dice el texto — las que faltan se crean, las que sobran
se borran.
"""

from __future__ import annotations

import re

from sqlmodel import Session, select

from ..engine import CycleError, ScheduleError
from ..models import Dependency, Task, TipoDependencia
from . import schedule as schedule_service
from .tasks import TareaInvalida

_REFERENCIA = re.compile(
    r"^([0-9]+(?:\.[0-9]+)*)\s*(FS|SS|FF)?\s*([+-]\s*[0-9]{1,3})?$", re.IGNORECASE
)
# El mismo tope que DependenciaIn: la grilla arma el modelo directo, sin Pydantic.
_LAG_MAXIMO = 365


def parsear(crudo: str) -> tuple[str, int, TipoDependencia] | None:
    """`1.3SS+2` → («1.3», 2, SS). Devuelve None si no tiene la forma esperada.

    Notación de MS Project: sin sufijo es Fin→Inicio, que es el caso normal.
    Lo usan tanto la grilla como el importador, para que una planilla escrita a
    mano signifique lo mismo que si lo escribieras en la celda.
    """
    referencia = _REFERENCIA.match(crudo.strip())
    if referencia is None:
        return None
    codigo, tipo_crudo, lag_crudo = referencia.groups()
    tipo = TipoDependencia((tipo_crudo or "FS").upper())
    return codigo, int((lag_crudo or "0").replace(" ", "")), tipo


def escribir(codigo: str, lag: int, tipo: TipoDependencia) -> str:
    """La forma inversa de `parsear`: lo que se muestra en la celda."""
    texto = codigo + ("" if tipo is TipoDependencia.FS else tipo.value)
    if lag > 0:
        texto += f"+{lag}"
    elif lag < 0:
        texto += str(lag)
    return texto


def texto_de(session: Session, project_id: int, task_id: int) -> str:
    """Cómo se muestra la celda: los códigos de las predecesoras, con tipo y lag."""
    codigos = {
        t.id: t.codigo
        for t in session.exec(select(Task).where(Task.project_id == project_id))
    }
    partes = [
        escribir(codigos.get(d.predecessor_id) or str(d.predecessor_id), d.lag, d.tipo)
        for d in session.exec(
            select(Dependency).where(
                Dependency.project_id == project_id, Dependency.successor_id == task_id
            )
        )
    ]
    return ", ".join(sorted(partes))


def guardar(session: Session, project_id: int, task_id: int, texto: str) -> list[str]:
    """Deja las predecesoras de la tarea igual a lo escrito. Devuelve los avisos."""
    tareas = list(session.exec(select(Task).where(Task.project_id == project_id)))
    por_codigo = {t.codigo: t for t in tareas if t.codigo}
    avisos: list[str] = []

    pedidas: dict[int, tuple[int, TipoDependencia]] = {}
    for crudo in texto.replace(";", ",").split(","):
        crudo = crudo.strip()
        if not crudo:
            continue
        referencia = parsear(crudo)
        if referencia is None:
            avisos.append(
                f"«{crudo}» no se entiende: se escribe 1.3, 1.3+2, 1.3SS o 1.3FF"
            )
            continue
        codigo, lag, tipo = referencia
        if abs(lag) > _LAG_MAXIMO:
            avisos.append(f"«{crudo}»: el lag no puede superar ±{_LAG_MAXIMO} días hábiles")
            continue
        predecesora = por_codigo.get(codigo)
        if predecesora is None:
            avisos.append(f"No existe ninguna tarea con código {codigo}")
            continue
        if predecesora.id == task_id:
            avisos.append("Una tarea no puede depender de sí misma")
            continue
        pedidas[predecesora.id] = (lag, tipo)

    return _sincronizar(session, project_id, task_id, pedidas, avisos)


def _sincronizar(
    session: Session,
    project_id: int,
    task_id: int,
    pedidas: dict[int, tuple[int, TipoDependencia]],
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

    for predecesora_id, (lag, tipo) in pedidas.items():
        existente = actuales.get(predecesora_id)
        if existente is not None and existente.lag == lag and existente.tipo == tipo:
            continue
        if existente is not None:
            existente.lag, existente.tipo = lag, tipo
            session.add(existente)
            session.commit()
            continue
        candidata = Dependency(
            project_id=project_id,
            predecessor_id=predecesora_id,
            successor_id=task_id,
            lag=lag,
            tipo=tipo,
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


__all__ = ["texto_de", "guardar", "parsear", "escribir", "borrar_de_tarea", "TareaInvalida"]
