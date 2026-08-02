"""Administración de cuentas. Solo para el admin: no hay auto-registro en la app."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from ..auth.dependencias import exige_admin
from ..db import get_session
from ..models_auth import Usuario
from ..services import usuarios as usuarios_service
from ..services.usuarios import CuentaInvalida
from ..templating import templates

router = APIRouter(prefix="/admin")


@router.get("/usuarios", response_class=HTMLResponse)
def listado(
    request: Request,
    aviso: str = "",
    session: Session = Depends(get_session),
    admin: Usuario = Depends(exige_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin/usuarios.html", {
        "usuarios": usuarios_service.listar(session),
        "aviso": aviso.strip()[:500] or None,
    })


@router.post("/usuarios")
def crear(
    mail: str = Form(...),
    nombre: str = Form(""),
    es_admin: str = Form(""),
    session: Session = Depends(get_session),
    admin: Usuario = Depends(exige_admin),
):
    """El admin no elige la contraseña: se genera y se muestra una sola vez."""
    provisoria = secrets.token_urlsafe(9)
    try:
        usuario = usuarios_service.crear(
            session, mail, provisoria, nombre=nombre,
            es_admin=es_admin.strip() in {"1", "true", "on", "sí", "si"},
        )
    except CuentaInvalida as error:
        return _volver(str(error))
    return _volver(
        f"Cuenta {usuario.mail} creada. Contraseña de un solo uso: {provisoria} "
        "— pasásela por un canal seguro; la cambia al primer ingreso."
    )


@router.post("/usuarios/{usuario_id}/password")
def resetear(
    usuario_id: int,
    session: Session = Depends(get_session),
    admin: Usuario = Depends(exige_admin),
):
    provisoria = secrets.token_urlsafe(9)
    try:
        usuario = usuarios_service.resetear_password(session, usuario_id, provisoria)
    except CuentaInvalida as error:
        return _volver(str(error))
    return _volver(
        f"Contraseña de {usuario.mail} reseteada: {provisoria} — sus sesiones se cerraron."
    )


@router.post("/usuarios/{usuario_id}/activo")
def activar(
    usuario_id: int,
    activo: str = Form("1"),
    session: Session = Depends(get_session),
    admin: Usuario = Depends(exige_admin),
):
    prendido = activo.strip() in {"1", "true", "on", "sí", "si"}
    try:
        usuario = usuarios_service.cambiar_activo(session, usuario_id, prendido)
    except CuentaInvalida as error:
        return _volver(str(error))
    estado = "activada" if prendido else "desactivada (sus sesiones se cerraron)"
    return _volver(f"Cuenta {usuario.mail} {estado}")


def _volver(aviso: str) -> RedirectResponse:
    destino = "/admin/usuarios"
    if aviso:
        destino += "?" + urlencode({"aviso": aviso})
    return RedirectResponse(destino, status_code=303)
