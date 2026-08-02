"""Login, salida, mi cuenta y el primer admin. HTTP puro sobre `services/usuarios`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from ..auth import sesion as sesion_service
from ..auth.dependencias import exige_usuario
from ..config import settings
from ..db import get_session
from ..models_auth import Usuario
from ..services import usuarios as usuarios_service
from ..services.usuarios import CredencialesInvalidas, CuentaInvalida
from ..templating import templates

router = APIRouter()


def _destino_seguro(siguiente: str) -> str:
    """Solo rutas internas: un `siguiente` con host ajeno es un open redirect."""
    limpio = (siguiente or "").strip()
    if limpio.startswith("/") and not limpio.startswith("//"):
        return limpio
    return "/"


@router.get("/ingresar", response_class=HTMLResponse)
def formulario_ingreso(
    request: Request, siguiente: str = "", session: Session = Depends(get_session)
) -> HTMLResponse:
    if not usuarios_service.hay_alguno(session):
        return RedirectResponse("/primer-usuario", status_code=303)
    return templates.TemplateResponse(
        request, "auth/ingresar.html", {"siguiente": _destino_seguro(siguiente), "error": None}
    )


@router.post("/ingresar")
def ingresar(
    request: Request,
    mail: str = Form(...),
    password: str = Form(...),
    siguiente: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        usuario = usuarios_service.autenticar(session, mail, password)
    except CredencialesInvalidas as error:
        return templates.TemplateResponse(
            request,
            "auth/ingresar.html",
            {"siguiente": _destino_seguro(siguiente), "error": str(error)},
            status_code=401,
        )

    abierta = sesion_service.abrir(
        session, usuario, agente=request.headers.get("user-agent", "")
    )
    destino = "/mi-cuenta" if usuario.debe_cambiar_password else _destino_seguro(siguiente)
    respuesta = RedirectResponse(destino, status_code=303)
    sesion_service.poner_cookie(respuesta, abierta.token, seguro=settings.cookie_segura)
    return respuesta


@router.post("/salir")
def salir(request: Request, session: Session = Depends(get_session)):
    sesion_service.cerrar(session, request.cookies.get(sesion_service.COOKIE, ""))
    respuesta = RedirectResponse("/ingresar", status_code=303)
    sesion_service.borrar_cookie(respuesta)
    return respuesta


@router.get("/primer-usuario", response_class=HTMLResponse)
def formulario_primer_usuario(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    """Solo mientras no exista ninguna cuenta: crea el admin inicial."""
    if usuarios_service.hay_alguno(session):
        return RedirectResponse("/ingresar", status_code=303)
    return templates.TemplateResponse(request, "auth/primer_usuario.html", {"error": None})


@router.post("/primer-usuario")
def crear_primer_usuario(
    request: Request,
    mail: str = Form(...),
    nombre: str = Form(""),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    if usuarios_service.hay_alguno(session):
        return RedirectResponse("/ingresar", status_code=303)
    try:
        usuario = usuarios_service.crear(
            session, mail, password, nombre=nombre, es_admin=True, debe_cambiar=False
        )
    except CuentaInvalida as error:
        return templates.TemplateResponse(
            request, "auth/primer_usuario.html", {"error": str(error)}, status_code=400
        )

    abierta = sesion_service.abrir(session, usuario)
    respuesta = RedirectResponse("/", status_code=303)
    sesion_service.poner_cookie(respuesta, abierta.token, seguro=settings.cookie_segura)
    return respuesta


@router.get("/mi-cuenta", response_class=HTMLResponse)
def mi_cuenta(
    request: Request, usuario: Usuario = Depends(exige_usuario)
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "auth/mi_cuenta.html", {"error": None, "hecho": False}
    )


@router.post("/mi-cuenta", response_class=HTMLResponse)
def cambiar_mi_password(
    request: Request,
    actual: str = Form(...),
    nueva: str = Form(...),
    repetida: str = Form(...),
    usuario: Usuario = Depends(exige_usuario),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        usuarios_service.cambiar_password(session, usuario, actual, nueva, repetida)
    except CuentaInvalida as error:
        return templates.TemplateResponse(
            request, "auth/mi_cuenta.html", {"error": str(error), "hecho": False},
            status_code=400,
        )
    # El cambio cerró todas las sesiones, incluida esta: hay que volver a entrar.
    respuesta = RedirectResponse("/ingresar", status_code=303)
    sesion_service.borrar_cookie(respuesta)
    return respuesta
