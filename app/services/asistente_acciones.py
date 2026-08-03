"""Las acciones que el asistente puede proponer, y su aplicación (Fase 29b).

El contrato es un conjunto **cerrado**: crear tarea, modificar título/duración/
criticidad y reescribir predecesoras — nada más. Ninguna acción se aplica sin la
confirmación explícita del usuario: este módulo recibe las acciones ya
confirmadas, las re-valida desde cero (vuelven del navegador: input externo) y
las ejecuta **solo vía services**, que ya rechazan ciclos, WBS colgantes y
valores fuera de rango. Lo inválido se descarta con aviso; jamás un 500.
"""

from __future__ import annotations

import json
from typing import Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlmodel import Session

from ..models import Task
from ..schemas import TareaIn
from . import arbol as arbol_service
from . import contactos as contactos_service
from . import predecesoras as predecesoras_service
from . import tasks as tasks_service
from .tasks import TareaInvalida

MAX_ACCIONES = 20


class CrearTarea(BaseModel):
    tipo: Literal["crear_tarea"]
    titulo: str = Field(min_length=1, max_length=200)
    padre_wbs: str = Field(default="", max_length=40)
    duracion: int = Field(default=1, ge=0, le=3650)
    predecesoras: str = Field(default="", max_length=400)
    critica: bool = False

    @property
    def descripcion(self) -> str:
        donde = f"bajo {self.padre_wbs}" if self.padre_wbs else "en el primer nivel"
        detalle = ["hito" if self.duracion == 0 else f"{self.duracion}d"]
        if self.critica:
            detalle.append("crítica")
        if self.predecesoras:
            detalle.append(f"después de {self.predecesoras}")
        return f"Crear «{self.titulo}» {donde} ({', '.join(detalle)})"


class ModificarTarea(BaseModel):
    tipo: Literal["modificar_tarea"]
    wbs: str = Field(min_length=1, max_length=40)
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    duracion: int | None = Field(default=None, ge=0, le=3650)
    critica: bool | None = None

    @property
    def descripcion(self) -> str:
        cambios = []
        if self.titulo is not None:
            cambios.append(f"título → «{self.titulo}»")
        if self.duracion is not None:
            cambios.append(f"duración → {self.duracion}d")
        if self.critica is not None:
            cambios.append("marcarla crítica" if self.critica else "sacarle la criticidad")
        return f"Modificar {self.wbs}: {'; '.join(cambios) or 'sin cambios'}"


class CambiarPredecesoras(BaseModel):
    tipo: Literal["cambiar_predecesoras"]
    wbs: str = Field(min_length=1, max_length=40)
    # La lista completa que queda, como en la celda: la fuente de verdad.
    predecesoras: str = Field(default="", max_length=400)

    @property
    def descripcion(self) -> str:
        if self.predecesoras:
            return f"Predecesoras de {self.wbs} → {self.predecesoras}"
        return f"Quitar todas las predecesoras de {self.wbs}"


Accion = Union[CrearTarea, ModificarTarea, CambiarPredecesoras]
_ADAPTADOR: TypeAdapter = TypeAdapter(Accion)


def parsear(crudas) -> tuple[list[Accion], list[str]]:
    """Valida cada acción por separado: una rota se descarta con aviso, no tumba el resto."""
    if not isinstance(crudas, list):
        return [], ["Las acciones propuestas no tienen la forma esperada: se descartaron"]

    acciones: list[Accion] = []
    avisos: list[str] = []
    for cruda in crudas[:MAX_ACCIONES]:
        try:
            acciones.append(_ADAPTADOR.validate_python(cruda))
        except ValidationError:
            avisos.append(
                f"Una acción propuesta no se entendió y se descartó: {str(cruda)[:80]}"
            )
    if len(crudas) > MAX_ACCIONES:
        avisos.append(
            f"El asistente propuso más de {MAX_ACCIONES} acciones: solo se toman las primeras"
        )
    return acciones, avisos


def desde_json(carga: str) -> tuple[list[Accion], list[str]]:
    """La carga que vuelve del navegador con la confirmación. Cero confianza."""
    try:
        crudas = json.loads(carga)
    except (json.JSONDecodeError, TypeError):
        return [], ["Se perdió la propuesta del asistente. Volvé a preguntar."]
    return parsear(crudas)


def a_json(acciones: list[Accion]) -> str:
    """Para el campo oculto de la confirmación, como hace el import con su carga."""
    return json.dumps([a.model_dump() for a in acciones], ensure_ascii=False)


def aplicar(
    session: Session,
    project_id: int,
    acciones: list[Accion],
    usuario_id: int | None = None,
) -> list[str]:
    """Ejecuta las acciones ya confirmadas, cada una vía su service. Devuelve avisos.

    `usuario_id` es quién **confirmó**, y va al historial: lo propuso el modelo, pero
    lo aplicó una persona. Sin esto, los cambios del asistente serían los únicos sin
    firma en la auditoría (Fase 12).
    """
    avisos: list[str] = []
    for accion in acciones:
        try:
            avisos += _aplicar_una(session, project_id, accion, usuario_id)
        except TareaInvalida as error:
            avisos.append(f"{accion.descripcion}: {error}")
    return avisos


def _aplicar_una(
    session: Session, project_id: int, accion: Accion, usuario_id: int | None
) -> list[str]:
    if isinstance(accion, CrearTarea):
        return _crear(session, project_id, accion, usuario_id)
    if isinstance(accion, ModificarTarea):
        return _modificar(session, project_id, accion, usuario_id)
    return _cambiar_predecesoras(session, project_id, accion, usuario_id)


def _por_wbs(session: Session, project_id: int) -> dict[str, Task]:
    return {t.codigo: t for t in tasks_service.listar(session, project_id) if t.codigo}


def _crear(
    session: Session, project_id: int, accion: CrearTarea, usuario_id: int | None = None
) -> list[str]:
    avisos: list[str] = []
    padre_id = None
    if accion.padre_wbs:
        padre = _por_wbs(session, project_id).get(accion.padre_wbs)
        if padre is None:
            avisos.append(
                f"«{accion.titulo}»: el padre {accion.padre_wbs} no existe; va al primer nivel"
            )
        else:
            padre_id = padre.id

    tarea = arbol_service.agregar_al_final(
        session,
        project_id,
        TareaIn(
            titulo=accion.titulo,
            duracion=accion.duracion,
            critica=accion.critica,
            parent_id=padre_id,
        ),
        usuario_id,
    )
    if accion.predecesoras:
        avisos += predecesoras_service.guardar(
            session, project_id, tarea.id or 0, accion.predecesoras, usuario_id
        )
    return avisos


def _modificar(
    session: Session,
    project_id: int,
    accion: ModificarTarea,
    usuario_id: int | None = None,
) -> list[str]:
    tarea = _por_wbs(session, project_id).get(accion.wbs)
    if tarea is None:
        return [f"No existe ninguna tarea con código {accion.wbs}: no se modificó nada"]

    responsable = ""
    if tarea.responsable_id is not None:
        contacto = contactos_service.obtener(session, tarea.responsable_id)
        responsable = contacto.nombre if contacto is not None else ""

    datos = TareaIn(
        titulo=accion.titulo if accion.titulo is not None else tarea.titulo,
        notas=tarea.notas,
        responsable=responsable,
        critica=accion.critica if accion.critica is not None else tarea.critica,
        ambito=tarea.ambito,
        peso=tarea.peso,
        avance=tarea.avance,
        duracion=accion.duracion if accion.duracion is not None else tarea.duracion,
        duracion_optimista=tarea.duracion_optimista,
        duracion_pesimista=tarea.duracion_pesimista,
        snet=tarea.snet,
        estado_id=tarea.estado_id,
    )
    tasks_service.actualizar(session, tarea.id or 0, datos, usuario_id)
    return []


def _cambiar_predecesoras(
    session: Session,
    project_id: int,
    accion: CambiarPredecesoras,
    usuario_id: int | None = None,
) -> list[str]:
    tarea = _por_wbs(session, project_id).get(accion.wbs)
    if tarea is None:
        return [f"No existe ninguna tarea con código {accion.wbs}: no se tocaron dependencias"]
    if tasks_service.tiene_hijas(session, tarea.id or 0):
        return [f"{accion.wbs} tiene subtareas: las dependencias van en las tareas hoja"]
    return predecesoras_service.guardar(
        session, project_id, tarea.id or 0, accion.predecesoras, usuario_id
    )
