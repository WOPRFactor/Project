"""Puente models → engine → cronograma.

Es el único lugar donde los modelos de SQLModel se traducen a las dataclasses del
motor. El motor nunca ve una Session.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from ..engine import (
    DependencyEdge,
    Schedule,
    ScheduleError,
    Escenario,
    TaskNode,
    TipoDependencia,
    calcular as motor_calcular,
    marcar,
)
from ..models import Dependency, Project, Task


def _nodos(tareas: list[Task]) -> list[TaskNode]:
    return [
        TaskNode(
            id=t.id or 0,
            titulo=t.titulo,
            parent_id=t.parent_id,
            duracion=t.duracion,
            snet=t.snet,
            orden=t.orden,
            duracion_optimista=t.duracion_optimista,
            duracion_pesimista=t.duracion_pesimista,
        )
        for t in tareas
    ]


def _aristas(dependencias: list[Dependency]) -> list[DependencyEdge]:
    return [
        DependencyEdge(
            predecessor_id=d.predecessor_id,
            successor_id=d.successor_id,
            lag=d.lag,
            tipo=TipoDependencia(d.tipo.value),
        )
        for d in dependencias
    ]


def calcular(
    session: Session,
    project_id: int,
    extra: list[Dependency] | None = None,
    escenario: Escenario = Escenario.PROBABLE,
) -> Schedule:
    """Cronograma del proyecto con holguras y ruta crítica marcadas.

    `extra` permite probar dependencias candidatas antes de guardarlas.
    Lanza ScheduleError si el árbol o el grafo son inválidos.
    """
    proyecto = session.get(Project, project_id)
    if proyecto is None:
        return Schedule()

    tareas = list(session.exec(select(Task).where(Task.project_id == project_id)))
    dependencias = list(
        session.exec(select(Dependency).where(Dependency.project_id == project_id))
    )
    dependencias.extend(extra or [])

    nodos = _nodos(tareas)
    aristas = _aristas(dependencias)
    cronograma = motor_calcular(proyecto.fecha_inicio, nodos, aristas, escenario)
    return marcar(
        cronograma, nodos, aristas, _topes_por_ambito(tareas, cronograma), escenario
    )


def _topes_por_ambito(tareas: list[Task], cronograma: Schedule) -> dict[int, date]:
    """Contra qué fecha se mide la holgura de cada tarea: el fin de *su* bloque.

    Medir todo contra el fin global regala margen: el acompañamiento posterior
    corre meses después del cierre, y contra esa fecha hasta la firma del acta
    aparece con medio año de aire.
    """
    fin_de: dict[str, date] = {}
    for tarea in tareas:
        calculada = cronograma.get(tarea.id or 0)
        if calculada is None or calculada.es_resumen:
            continue
        clave = tarea.ambito.value
        if clave not in fin_de or calculada.fin > fin_de[clave]:
            fin_de[clave] = calculada.fin
    return {
        t.id: fin_de[t.ambito.value]
        for t in tareas
        if t.id is not None and t.ambito.value in fin_de
    }


def calcular_seguro(session: Session, project_id: int) -> tuple[Schedule, str | None]:
    """Igual que `calcular`, pero devuelve el error como texto en vez de propagarlo.

    Las vistas usan esta versión: un grafo inválido muestra un aviso, nunca un 500.
    """
    try:
        return calcular(session, project_id), None
    except ScheduleError as error:
        return Schedule(), str(error)


def ventana(
    session: Session, project_id: int, fin_probable: date | None = None
) -> dict[str, date | None]:
    """Fin del proyecto en los tres escenarios.

    Con tareas de duración estimada, un fin único es una precisión que no se tiene:
    lo defendible es la ventana. Si nadie declaró rangos, los tres coinciden.

    `fin_probable` permite reusar el cronograma que el llamador ya calculó, en vez
    de correr el escenario probable de nuevo en el mismo render.
    """
    salida: dict[str, date | None] = {}
    for escenario in Escenario:
        if escenario is Escenario.PROBABLE and fin_probable is not None:
            salida[escenario.value] = fin_probable
            continue
        try:
            plan = calcular(session, project_id, escenario=escenario)
        except ScheduleError:
            return {e.value: None for e in Escenario}
        salida[escenario.value] = plan.fin
    return salida
