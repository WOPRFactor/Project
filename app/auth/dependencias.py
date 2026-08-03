"""Quién está pidiendo: las dependencias que usan los routers.

`exige_usuario` es la puerta: sin sesión válida, redirige al login (o 401 si el
pedido vino por HTMX, que no sigue redirects de forma útil). El chequeo de CSRF
va en el middleware, no acá, porque tiene que cubrir **todas** las rutas mutantes
sin depender de que cada router se acuerde de pedirlo.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..db import get_session
from ..models import Project
from ..models_auth import Rol, Usuario
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


@dataclass(frozen=True)
class UsuarioVista:
    """Foto del usuario para las plantillas, desprendida del ORM.

    Guardar la entidad de SQLModel en `request.state` funciona hasta que algo
    renderiza **después** de que la sesión de base se cerró —una página de error,
    por ejemplo—: ahí el objeto está desconectado y leerle un atributo revienta.
    Una foto inmutable no tiene ese problema.
    """

    id: int
    mail: str
    nombre: str
    es_admin: bool
    debe_cambiar_password: bool

    @classmethod
    def de(cls, usuario: Usuario) -> "UsuarioVista":
        return cls(
            id=usuario.id or 0,
            mail=usuario.mail,
            nombre=usuario.nombre,
            es_admin=usuario.es_admin,
            debe_cambiar_password=usuario.debe_cambiar_password,
        )


def exige_usuario(
    request: Request, session: Session = Depends(get_session)
) -> Usuario:
    """Sesión obligatoria. Deja la foto en request.state para las plantillas."""
    token = request.cookies.get(sesion_service.COOKIE, "")
    usuario = sesion_service.leer(session, token)
    if usuario is None:
        raise RedirigirALogin(destino=str(request.url.path))
    request.state.usuario = UsuarioVista.de(usuario)
    return usuario


def exige_admin(usuario: Usuario = Depends(exige_usuario)) -> Usuario:
    if not usuario.es_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta pantalla es solo para el administrador",
        )
    return usuario


@dataclass
class Acceso:
    """Un proyecto que este usuario **sí** puede ver, con su rol resuelto.

    Es el objeto que reemplaza al `project_id` crudo en los routers: si lo tenés
    en la mano, es porque la entidad existe y el permiso ya se verificó. No se
    puede construir salteando el chequeo.
    """

    proyecto: Project
    # La foto, no la entidad: este objeto llega a las plantillas.
    usuario: UsuarioVista
    rol: Rol

    @property
    def id(self) -> int:
        return self.proyecto.id or 0

    @property
    def puede_editar(self) -> bool:
        return self.rol in (Rol.duenio, Rol.editor)

    @property
    def es_duenio(self) -> bool:
        return self.rol is Rol.duenio


def _resolver(session: Session, project_id: int, usuario: Usuario) -> Acceso:
    """Entidad y permiso en un solo paso.

    Un no-miembro recibe **404 y no 403**: un 403 confirmaría que el proyecto
    existe, que es justo lo que no queremos filtrar. Para quien no tiene acceso,
    el proyecto sencillamente no está.
    """
    from ..services import miembros as miembros_service

    proyecto = session.get(Project, project_id)
    if proyecto is None:
        raise SinAcceso()

    rol = miembros_service.rol_de(session, project_id, usuario.id or 0)
    if rol is None:
        # El admin de la instancia entra a todo, como dueño.
        if usuario.es_admin:
            return Acceso(proyecto=proyecto, usuario=UsuarioVista.de(usuario), rol=Rol.duenio)
        raise SinAcceso()
    return Acceso(proyecto=proyecto, usuario=UsuarioVista.de(usuario), rol=rol)


class SinAcceso(Exception):
    """No existe, o existe y no es tuyo: para el usuario es lo mismo (404)."""


def exige_lector(
    project_id: int,
    request: Request,
    usuario: Usuario = Depends(exige_usuario),
    session: Session = Depends(get_session),
) -> Acceso:
    """Ver el proyecto. El piso: todo miembro llega hasta acá."""
    acceso = _resolver(session, project_id, usuario)
    request.state.acceso = acceso
    return acceso


def exige_editor(acceso: Acceso = Depends(exige_lector)) -> Acceso:
    """Modificar el cronograma. Un lector recibe 403: sabe que existe, no puede."""
    if not acceso.puede_editar:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenés acceso de solo lectura a este proyecto",
        )
    return acceso


def exige_duenio(acceso: Acceso = Depends(exige_lector)) -> Acceso:
    """Miembros, línea base y borrar el proyecto."""
    if not acceso.es_duenio:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esto solo lo puede hacer el dueño del proyecto",
        )
    return acceso


def respuesta_sin_sesion(request: Request, destino: str) -> RedirectResponse:
    """Un GET normal va al login; un pedido HTMX recibe 401 con la orden de recargar."""
    if request.headers.get("hx-request"):
        respuesta = RedirectResponse("/ingresar", status_code=status.HTTP_303_SEE_OTHER)
        respuesta.status_code = status.HTTP_401_UNAUTHORIZED
        respuesta.headers["HX-Redirect"] = "/ingresar"
        return respuesta
    siguiente = f"?siguiente={destino}" if destino and destino != "/" else ""
    return RedirectResponse(f"/ingresar{siguiente}", status_code=status.HTTP_303_SEE_OTHER)
