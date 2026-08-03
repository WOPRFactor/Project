"""Rutas de la grilla. Toda edición recalcula el cronograma y devuelve el tablero."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlmodel import Session

from ..auth.dependencias import Acceso, exige_editor, exige_lector
from ..db import get_session
from ..schemas import ProyectoIn, TareaIn
from ..services import arbol as arbol_service
from ..services import pesos_aplicar
from ..services import predecesoras as predecesoras_service
from ..services import projects as projects_service
from ..services import riesgos as riesgos_service
from ..services import tasks as tasks_service
from ..services.riesgos import RiesgoInvalido
from ..services.tasks import TareaInvalida
from . import _celda
from ._tablero import Mirada, mirada_form, render

router = APIRouter(prefix="/proyectos/{project_id}", dependencies=[Depends(exige_editor)])


@router.post("/tareas/agregar", response_class=HTMLResponse)
def agregar(
    project_id: int,
    request: Request,
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        arbol_service.agregar_al_final(session, project_id, TareaIn(titulo="Tarea nueva"))
    except TareaInvalida as error:
        return render(request, session, project_id, aviso=str(error), mirada=mirada)
    return render(request, session, project_id, mirada=mirada)


@router.post("/tareas/{task_id}/celda", response_class=HTMLResponse)
def guardar_celda(
    project_id: int,
    task_id: int,
    request: Request,
    titulo: str = Form(...),
    codigo: str | None = Form(None),
    responsable: str | None = Form(None),
    predecesoras: str | None = Form(None),
    duracion: str = Form(""),
    inicio: str | None = Form(None),
    critica: str | None = Form(None),
    ambito: str | None = Form(None),
    estado_id: str = Form(""),
    peso: str | None = Form(None),
    avance: str = Form(""),
    duracion_optimista: str | None = Form(None),
    duracion_pesimista: str | None = Form(None),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Guarda la fila completa. Los campos que no viajan (None) son columnas
    apagadas: se conserva lo que la tarea ya tiene en vez de pisarlo con defaults."""
    tarea = tasks_service.obtener(session, task_id)
    if tarea is None or tarea.project_id != project_id:
        return render(request, session, project_id, aviso="Esa tarea ya no existe", mirada=mirada)

    fila = _celda.FilaCruda(
        titulo=titulo, responsable=responsable, duracion=duracion, inicio=inicio,
        critica=critica, ambito=ambito, estado_id=estado_id, peso=peso, avance=avance,
        duracion_optimista=duracion_optimista, duracion_pesimista=duracion_pesimista,
    )
    try:
        datos = _celda.a_tarea(session, tarea, fila)
    except (ValidationError, ValueError) as error:
        return render(request, session, project_id, aviso=_mensaje(error), mirada=mirada)

    tasks_service.actualizar(session, task_id, datos)

    avisos: list[str] = []
    if codigo is not None:
        aviso_codigo = arbol_service.guardar_codigo(session, task_id, codigo)
        if aviso_codigo:
            avisos.append(aviso_codigo)
    if predecesoras is not None and not tasks_service.tiene_hijas(session, task_id):
        avisos += predecesoras_service.guardar(session, project_id, task_id, predecesoras)
    return render(request, session, project_id, aviso="; ".join(avisos) or None, mirada=mirada)


@router.post("/tareas/{task_id}/insertar", response_class=HTMLResponse)
def insertar(
    project_id: int,
    task_id: int,
    request: Request,
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    return _mover(request, session, project_id, arbol_service.insertar_debajo, task_id, mirada)


@router.post("/tareas/{task_id}/indentar", response_class=HTMLResponse)
def indentar(
    project_id: int,
    task_id: int,
    request: Request,
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    return _mover(request, session, project_id, arbol_service.indentar, task_id, mirada)


@router.post("/tareas/{task_id}/desindentar", response_class=HTMLResponse)
def desindentar(
    project_id: int,
    task_id: int,
    request: Request,
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    return _mover(request, session, project_id, arbol_service.desindentar, task_id, mirada)


@router.post("/tareas/{task_id}/estado", response_class=HTMLResponse)
def cambiar_estado(
    project_id: int,
    task_id: int,
    request: Request,
    estado_id: int = Form(...),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    tasks_service.cambiar_estado(session, task_id, estado_id)
    return render(request, session, project_id, mirada=mirada)


@router.post("/tareas/{task_id}/eliminar", response_class=HTMLResponse)
def eliminar(
    project_id: int,
    task_id: int,
    request: Request,
    promover: bool = Form(False),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    tasks_service.eliminar(session, task_id, promover_hijas=promover)
    return render(request, session, project_id, mirada=mirada)


@router.post("/inicio", response_class=HTMLResponse)
def cambiar_inicio(
    project_id: int,
    request: Request,
    fecha_inicio: str = Form(...),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Mueve el arranque del proyecto: todo el cronograma se recalcula detrás."""
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return render(request, session, project_id, aviso="Ese proyecto ya no existe", mirada=mirada)
    try:
        nueva = date.fromisoformat(fecha_inicio.strip())
    except ValueError:
        return render(request, session, project_id, aviso="Esa fecha no es válida", mirada=mirada)

    anterior = proyecto.fecha_inicio
    projects_service.actualizar(
        session,
        project_id,
        ProyectoIn(
            nombre=proyecto.nombre,
            descripcion=proyecto.descripcion,
            fecha_inicio=nueva,
            estado=proyecto.estado,
        ),
    )
    corrimiento = (nueva - anterior).days
    aviso = None if not corrimiento else (
        f"Arranque movido {corrimiento:+d} días: el cronograma se recalculó entero"
    )
    return render(request, session, project_id, aviso=aviso, mirada=mirada)


@router.post("/tareas/{task_id}/riesgo", response_class=HTMLResponse)
def marcar_riesgo(
    project_id: int,
    task_id: int,
    request: Request,
    tildado: str = Form("1"),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Tilde de la grilla: crea un borrador de riesgo o saca el que sigue vacío."""
    try:
        aviso = riesgos_service.marcar_tarea(
            session, project_id, task_id, tildado.strip() == "1"
        )
    except RiesgoInvalido as error:
        return render(request, session, project_id, aviso=str(error), mirada=mirada)
    return render(request, session, project_id, aviso=aviso or None, mirada=mirada)


@router.post("/pesos/repartir", response_class=HTMLResponse)
def repartir_pesos(
    project_id: int,
    request: Request,
    criterio: str = Form("parejo"),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Punto de partida para los pesos. Pisa lo cargado: la confirmación lo avisa."""
    if criterio == "limpiar":
        cambiadas = pesos_aplicar.limpiar(session, project_id)
        return render(
            request, session, project_id,
            aviso=f"{cambiadas} pesos borrados: vuelven al reparto automático parejo.",
            mirada=mirada,
        )
    cambiadas = pesos_aplicar.repartir(session, project_id, criterio)
    como = "por duración" if criterio == pesos_aplicar.POR_DURACION else "en partes iguales"
    return render(
        request, session, project_id,
        aviso=f"{cambiadas} pesos repartidos {como}. Ajustá lo que no represente el valor real.",
        mirada=mirada,
    )


@router.post("/renumerar", response_class=HTMLResponse)
def renumerar(
    project_id: int,
    request: Request,
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    cambiados = arbol_service.renumerar(session, project_id)
    return render(request, session, project_id, aviso=f"{cambiados} códigos reasignados", mirada=mirada)


def _mover(request: Request, session: Session, project_id: int, operacion, task_id: int, mirada):
    try:
        operacion(session, task_id)
    except TareaInvalida as error:
        return render(request, session, project_id, aviso=str(error), mirada=mirada)
    return render(request, session, project_id, mirada=mirada)


def _mensaje(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(e.get("msg", "dato inválido") for e in error.errors())
    return str(error) or "No se pudo guardar"
