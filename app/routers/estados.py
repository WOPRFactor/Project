"""ABM de los estados de un proyecto. HTTP puro: parsear, llamar al service, renderizar."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlmodel import Session

from ..auth.dependencias import exige_usuario
from ..db import get_session
from ..models import ETIQUETA_COLOR
from ..schemas import EstadoIn
from ..services import estados as estados_service
from ..services import projects as projects_service
from ..services.estados import EstadoInvalido
from ..templating import templates

router = APIRouter(prefix="/proyectos/{project_id}/estados", dependencies=[Depends(exige_usuario)])


@router.get("", response_class=HTMLResponse)
def pantalla(
    project_id: int, request: Request, aviso: str = "", session: Session = Depends(get_session)
) -> HTMLResponse:
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return templates.TemplateResponse(
            request, "error.html", {"mensaje": "Ese proyecto no existe"}, status_code=404
        )
    return templates.TemplateResponse(request, "estados/lista.html", {
        "proyecto": proyecto,
        "estados": estados_service.asegurar_defaults(session, project_id),
        "colores": ETIQUETA_COLOR,
        "aviso": aviso or None,
    })


@router.post("")
def crear(
    project_id: int,
    nombre: str = Form(...),
    color: str = Form("gris"),
    es_final: str = Form("0"),
    avance_sugerido: str = Form("0"),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    return _aplicar(
        project_id,
        lambda datos: estados_service.crear(
            session, project_id, datos.nombre, datos.color,
            datos.es_final, datos.avance_sugerido,
        ),
        nombre, color, es_final, avance_sugerido,
    )


@router.post("/{estado_id}")
def actualizar(
    project_id: int,
    estado_id: int,
    nombre: str = Form(...),
    color: str = Form("gris"),
    es_final: str = Form("0"),
    avance_sugerido: str = Form("0"),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    estado = estados_service.obtener(session, estado_id)
    if estado is None or estado.project_id != project_id:
        return _volver(project_id, "Ese estado no es de este proyecto")
    return _aplicar(
        project_id,
        lambda datos: estados_service.actualizar(
            session, estado_id, datos.nombre, datos.color,
            datos.es_final, datos.avance_sugerido,
        ),
        nombre, color, es_final, avance_sugerido,
    )


@router.post("/{estado_id}/eliminar")
def eliminar(
    project_id: int,
    estado_id: int,
    reemplazo_id: str = Form(""),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    estado = estados_service.obtener(session, estado_id)
    if estado is None or estado.project_id != project_id:
        return _volver(project_id, "Ese estado no es de este proyecto")
    try:
        estados_service.eliminar(
            session, estado_id,
            int(reemplazo_id) if reemplazo_id.strip().isdigit() else None,
        )
    except EstadoInvalido as error:
        return _volver(project_id, str(error))
    return _volver(project_id, "Estado borrado; sus tareas quedaron reasignadas")


def _aplicar(project_id: int, operacion, nombre, color, es_final, avance) -> RedirectResponse:
    try:
        datos = EstadoIn(
            nombre=nombre,
            color=color,
            es_final=es_final.strip() in {"1", "true", "on", "sí", "si"},
            avance_sugerido=int(avance) if avance.strip().lstrip("-").isdigit() else 0,
        )
        operacion(datos)
    except ValidationError as error:
        return _volver(project_id, "; ".join(
            e.get("msg", "dato inválido") for e in error.errors()
        ))
    except EstadoInvalido as error:
        return _volver(project_id, str(error))
    return _volver(project_id, "")


def _volver(project_id: int, aviso: str) -> RedirectResponse:
    destino = f"/proyectos/{project_id}/estados"
    if aviso:
        # Se codifica a mano: `RedirectResponse` deja pasar `&` y `=` sin escapar, y
        # el aviso puede arrastrar texto que escribió el usuario.
        destino += "?" + urlencode({"aviso": aviso})
    return RedirectResponse(destino, status_code=303)
