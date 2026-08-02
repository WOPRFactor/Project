"""Quién está pidiendo: las dependencias que usan los routers.

`exige_usuario` es la puerta: sin sesión válida, redirige al login (o 401 si el
pedido vino por HTMX, que no sigue redirects de forma útil). El chequeo de CSRF
va en el middleware, no acá, porque tiene que cubrir **todas** las rutas mutantes
sin depender de que cada router se acuerde de pedirlo.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..db import get_session
from ..models_auth import Usuario
from . import sesion as sesion_service


class RedirigirALogin(Exception):
    """El pedido necesita sesión. El manejador global decide redirect o 401."""

    def __init__(self, destino: str = "/") -> None:
        self.destino = destino


def usuario_opcional(
    request: Request, session: Session = Depends(get_session)
) -> Usuario | None:
    """El usuario de la sesión, o None. Para páginas que funcionan sin cuenta."""
    token = request.cookies.get(sesion_service.COOKIE, "")
    return sesion_service.leer(session, token)


def exige_usuario(
    request: Request, session: Session = Depends(get_session)
) -> Usuario:
    """Sesión obligatoria. Guarda el usuario en request.state para las plantillas."""
    token = request.cookies.get(sesion_service.COOKIE, "")
    usuario = sesion_service.leer(session, token)
    if usuario is None:
        raise RedirigirALogin(destino=str(request.url.path))
    request.state.usuario = usuario
    return usuario


def exige_admin(usuario: Usuario = Depends(exige_usuario)) -> Usuario:
    if not usuario.es_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta pantalla es solo para el administrador",
        )
    return usuario


def respuesta_sin_sesion(request: Request, destino: str) -> RedirectResponse:
    """Un GET normal va al login; un pedido HTMX recibe 401 con la orden de recargar."""
    if request.headers.get("hx-request"):
        respuesta = RedirectResponse("/ingresar", status_code=status.HTTP_303_SEE_OTHER)
        respuesta.status_code = status.HTTP_401_UNAUTHORIZED
        respuesta.headers["HX-Redirect"] = "/ingresar"
        return respuesta
    siguiente = f"?siguiente={destino}" if destino and destino != "/" else ""
    return RedirectResponse(f"/ingresar{siguiente}", status_code=status.HTTP_303_SEE_OTHER)
