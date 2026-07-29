"""La fila de la grilla tal como viaja en el POST, y su traducción a TareaIn.

Las columnas apagadas no renderizan sus inputs, así que esos campos no llegan en
el formulario (None). None significa «conservar lo que la tarea ya tiene», que no
es lo mismo que "": una celda visible que el usuario vació.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session

from ..models import Ambito, Task
from ..schemas import TareaIn
from ..services import contactos as contactos_service
from ..services import schedule as schedule_service

_VERDADEROS = {"1", "true", "on", "sí", "si"}


@dataclass(frozen=True)
class FilaCruda:
    """Los campos de la fila, crudos. None = el input no viajó (columna apagada)."""

    titulo: str
    responsable: str | None = None
    duracion: str = ""
    inicio: str | None = None
    critica: str | None = None
    ambito: str | None = None
    estado_id: str = ""
    peso: str | None = None
    avance: str = ""
    duracion_optimista: str | None = None
    duracion_pesimista: str | None = None


def a_tarea(session: Session, tarea: Task, fila: FilaCruda) -> TareaIn:
    """Combina lo que viajó con lo que la tarea ya tiene.

    Puede levantar ValueError o ValidationError; el router las convierte en aviso.
    """
    return TareaIn(
        titulo=fila.titulo,
        notas=tarea.notas,
        responsable=_responsable(session, tarea, fila.responsable),
        critica=(
            tarea.critica
            if fila.critica is None
            else fila.critica.strip() in _VERDADEROS
        ),
        ambito=_ambito(tarea, fila.ambito),
        # Celda vacía = sin peso declarado, que no es lo mismo que peso cero:
        # significa "repartime lo que sobre".
        peso=_entero_o_actual(fila.peso, tarea.peso),
        avance=int(fila.avance) if fila.avance.strip() else tarea.avance,
        duracion=int(fila.duracion) if fila.duracion.strip() else tarea.duracion,
        duracion_optimista=_entero_o_actual(
            fila.duracion_optimista, tarea.duracion_optimista
        ),
        duracion_pesimista=_entero_o_actual(
            fila.duracion_pesimista, tarea.duracion_pesimista
        ),
        snet=_snet(session, tarea, fila.inicio),
        estado_id=int(fila.estado_id) if fila.estado_id.strip().isdigit() else tarea.estado_id,
    )


def _entero_o_actual(crudo: str | None, actual: int | None) -> int | None:
    if crudo is None:
        return actual
    return int(crudo) if crudo.strip() else None


def _ambito(tarea: Task, crudo: str | None) -> Ambito:
    if crudo is None:
        return tarea.ambito
    return Ambito(crudo) if crudo in Ambito.__members__ else tarea.ambito


def _responsable(session: Session, tarea: Task, crudo: str | None) -> str:
    if crudo is not None:
        return crudo
    if tarea.responsable_id is None:
        return ""
    actual = contactos_service.obtener(session, tarea.responsable_id)
    return actual.nombre if actual is not None else ""


def _snet(session: Session, tarea: Task, crudo: str | None) -> date | None:
    """La celda de Inicio muestra la fecha *calculada* cuando no hay SNET declarado.

    Si vuelve exactamente esa fecha, el usuario no la escribió: guardarla anclaría
    la tarea sin que nadie lo pida, y mover el arranque del proyecto dejaría de
    moverla. Solo una fecha distinta de la calculada se toma como restricción.
    """
    if crudo is None:
        return tarea.snet
    if not crudo.strip():
        return None
    escrito = date.fromisoformat(crudo.strip())
    if tarea.snet is None and escrito == _inicio_calculado(session, tarea):
        return None
    return escrito


def _inicio_calculado(session: Session, tarea: Task) -> date | None:
    cronograma, _ = schedule_service.calcular_seguro(session, tarea.project_id)
    calculada = cronograma.get(tarea.id or 0)
    return calculada.inicio if calculada is not None else None
