"""Rutas de la grilla. Toda edición recalcula el cronograma y devuelve el tablero."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlmodel import Session

from ..db import get_session
from ..models import Ambito
from ..schemas import ProyectoIn, TareaIn
from ..services import arbol as arbol_service
from ..services import importar_aplicar
from ..services import importar_excel
from ..services import importar_texto
from ..services import pesos_aplicar
from ..services import predecesoras as predecesoras_service
from ..services import projects as projects_service
from ..services import tasks as tasks_service
from ..services.tasks import TareaInvalida
from ._tablero import render

router = APIRouter(prefix="/proyectos/{project_id}")


@router.post("/tareas/agregar", response_class=HTMLResponse)
def agregar(
    project_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    arbol_service.agregar_al_final(session, project_id, TareaIn(titulo="Tarea nueva"))
    return render(request, session, project_id)


@router.post("/tareas/{task_id}/celda", response_class=HTMLResponse)
def guardar_celda(
    project_id: int,
    task_id: int,
    request: Request,
    codigo: str = Form(""),
    titulo: str = Form(...),
    responsable: str = Form(""),
    predecesoras: str = Form(""),
    duracion: str = Form(""),
    inicio: str = Form(""),
    critica: str = Form("0"),
    ambito: str = Form("proyecto"),
    estado_id: str = Form(""),
    peso: str = Form(""),
    duracion_optimista: str = Form(""),
    duracion_pesimista: str = Form(""),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Guarda la fila completa: el formulario manda todas sus celdas en cada cambio."""
    tarea = tasks_service.obtener(session, task_id)
    if tarea is None or tarea.project_id != project_id:
        return render(request, session, project_id, aviso="Esa tarea ya no existe")

    try:
        datos = TareaIn(
            titulo=titulo,
            notas=tarea.notas,
            responsable=responsable,
            critica=critica.strip() in {"1", "true", "on", "sí", "si"},
            ambito=Ambito(ambito) if ambito in Ambito.__members__ else Ambito.proyecto,
            # Celda vacía = sin peso declarado, que no es lo mismo que peso cero:
            # significa "repartime lo que sobre".
            peso=int(peso) if peso.strip() else None,
            duracion=int(duracion) if duracion.strip() else tarea.duracion,
            duracion_optimista=int(duracion_optimista) if duracion_optimista.strip() else None,
            duracion_pesimista=int(duracion_pesimista) if duracion_pesimista.strip() else None,
            snet=date.fromisoformat(inicio) if inicio.strip() else None,
            estado_id=int(estado_id) if estado_id.strip().isdigit() else tarea.estado_id,
        )
    except (ValidationError, ValueError) as error:
        return render(request, session, project_id, aviso=_mensaje(error))

    tasks_service.actualizar(session, task_id, datos)
    _guardar_codigo(session, task_id, codigo)

    avisos: list[str] = []
    if not tasks_service.tiene_hijas(session, task_id):
        avisos = predecesoras_service.guardar(session, project_id, task_id, predecesoras)
    return render(request, session, project_id, aviso="; ".join(avisos) or None)


@router.post("/tareas/{task_id}/insertar", response_class=HTMLResponse)
def insertar(
    project_id: int, task_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    return _mover(request, session, project_id, arbol_service.insertar_debajo, task_id)


@router.post("/tareas/{task_id}/indentar", response_class=HTMLResponse)
def indentar(
    project_id: int, task_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    return _mover(request, session, project_id, arbol_service.indentar, task_id)


@router.post("/tareas/{task_id}/desindentar", response_class=HTMLResponse)
def desindentar(
    project_id: int, task_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    return _mover(request, session, project_id, arbol_service.desindentar, task_id)


@router.post("/tareas/{task_id}/estado", response_class=HTMLResponse)
def cambiar_estado(
    project_id: int,
    task_id: int,
    request: Request,
    estado_id: int = Form(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    tasks_service.cambiar_estado(session, task_id, estado_id)
    return render(request, session, project_id)


@router.post("/tareas/{task_id}/eliminar", response_class=HTMLResponse)
def eliminar(
    project_id: int,
    task_id: int,
    request: Request,
    promover: bool = Form(False),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    tasks_service.eliminar(session, task_id, promover_hijas=promover)
    return render(request, session, project_id)


@router.post("/inicio", response_class=HTMLResponse)
def cambiar_inicio(
    project_id: int,
    request: Request,
    fecha_inicio: str = Form(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Mueve el arranque del proyecto: todo el cronograma se recalcula detrás."""
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return render(request, session, project_id, aviso="Ese proyecto ya no existe")
    try:
        nueva = date.fromisoformat(fecha_inicio.strip())
    except ValueError:
        return render(request, session, project_id, aviso="Esa fecha no es válida")

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
    return render(request, session, project_id, aviso=aviso)


@router.post("/pesos/repartir", response_class=HTMLResponse)
def repartir_pesos(
    project_id: int,
    request: Request,
    criterio: str = Form("parejo"),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Punto de partida para los pesos. Pisa lo cargado: la confirmación lo avisa."""
    if criterio == "limpiar":
        cambiadas = pesos_aplicar.limpiar(session, project_id)
        return render(
            request, session, project_id,
            aviso=f"{cambiadas} pesos borrados: vuelven al reparto automático parejo.",
        )
    cambiadas = pesos_aplicar.repartir(session, project_id, criterio)
    como = "por duración" if criterio == pesos_aplicar.POR_DURACION else "en partes iguales"
    return render(
        request, session, project_id,
        aviso=f"{cambiadas} pesos repartidos {como}. Ajustá lo que no represente el valor real.",
    )


@router.post("/renumerar", response_class=HTMLResponse)
def renumerar(
    project_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    cambiados = arbol_service.renumerar(session, project_id)
    return render(request, session, project_id, aviso=f"{cambiados} códigos reasignados")


@router.post("/importar", response_class=HTMLResponse)
async def importar_planilla(
    project_id: int,
    request: Request,
    archivo: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Suma las tareas de una planilla al proyecto abierto."""
    if not (archivo.filename or "").lower().endswith((".xlsx", ".xlsm")):
        return render(request, session, project_id, aviso="Tiene que ser un .xlsx o .xlsm")

    contenido = await archivo.read()
    if len(contenido) > 5 * 1024 * 1024:
        return render(request, session, project_id, aviso="La planilla supera los 5 MB")

    try:
        importacion = importar_excel.leer(contenido)
    except Exception:  # openpyxl levanta de todo con archivos corruptos
        return render(
            request, session, project_id,
            aviso="No pude leer la planilla: ¿está corrupta o protegida?",
        )
    if not importacion.filas:
        return render(
            request, session, project_id,
            aviso="No encontré tareas: la planilla necesita columnas «WBS» y «Tarea»",
        )

    avisos = importar_aplicar.agregar_a_proyecto(session, project_id, importacion)
    return render(request, session, project_id, aviso="; ".join(avisos) or None)


@router.post("/pegar", response_class=HTMLResponse)
def pegar(
    project_id: int,
    request: Request,
    texto: str = Form(""),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    if len(texto) > 200_000:
        return render(request, session, project_id, aviso="El texto pegado es demasiado grande")
    importacion = importar_texto.leer(texto)
    if not importacion.filas:
        return render(request, session, project_id, aviso="No encontré tareas en lo que pegaste")
    avisos = importar_aplicar.agregar_a_proyecto(session, project_id, importacion)
    return render(request, session, project_id, aviso="; ".join(avisos) or None)


def _mover(request: Request, session: Session, project_id: int, operacion, task_id: int):
    try:
        operacion(session, task_id)
    except TareaInvalida as error:
        return render(request, session, project_id, aviso=str(error))
    return render(request, session, project_id)


def _guardar_codigo(session: Session, task_id: int, codigo: str) -> None:
    tarea = tasks_service.obtener(session, task_id)
    limpio = codigo.strip()[:40]
    if tarea is not None and tarea.codigo != limpio:
        tarea.codigo = limpio
        session.add(tarea)
        session.commit()


def _mensaje(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(e.get("msg", "dato inválido") for e in error.errors())
    return str(error) or "No se pudo guardar"
