"""Sesiones: crear, leer, refrescar y revocar. La cookie lleva un token opaco.

El token se genera con `secrets.token_urlsafe(32)` y se guarda tal cual en la
tabla: no es un dato derivable ni firmado, así que robarlo es la única forma de
usarlo, y borrarlo de la tabla lo invalida al instante.

Dos vencimientos a propósito: por **inactividad** (te fuiste del escritorio) y por
**antigüedad** (una pestaña abierta hace un mes no vale). Se rota el token al
iniciar sesión, que es la defensa contra fijación de sesión.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import Response
from sqlmodel import Session, select

from ..models_auth import Sesion, Usuario

COOKIE = "wopr_sesion"
INACTIVIDAD = timedelta(hours=12)
ANTIGUEDAD = timedelta(days=14)


def abrir(session: Session, usuario: Usuario, agente: str = "") -> Sesion:
    """Sesión nueva para un login exitoso. El token es nuevo siempre (anti-fijación)."""
    ahora = datetime.now()
    sesion = Sesion(
        token=secrets.token_urlsafe(32),
        usuario_id=usuario.id or 0,
        creada_el=ahora,
        visto_el=ahora,
        expira_el=ahora + ANTIGUEDAD,
        agente=agente[:200],
    )
    usuario.ultimo_ingreso = ahora
    session.add(sesion)
    session.add(usuario)
    session.commit()
    session.refresh(sesion)
    return sesion


def leer(session: Session, token: str) -> Usuario | None:
    """El usuario de una sesión viva, refrescando la actividad. None si no vale.

    Una sesión vencida se borra en el momento en que se intenta usar: la tabla se
    limpia sola sin necesitar una tarea programada.
    """
    if not token:
        return None
    sesion = session.exec(select(Sesion).where(Sesion.token == token)).first()
    if sesion is None:
        return None

    ahora = datetime.now()
    if ahora > sesion.expira_el or ahora - sesion.visto_el > INACTIVIDAD:
        session.delete(sesion)
        session.commit()
        return None

    usuario = session.get(Usuario, sesion.usuario_id)
    if usuario is None or not usuario.activo:
        # Cuenta borrada o desactivada: la sesión no sobrevive al usuario.
        session.delete(sesion)
        session.commit()
        return None

    sesion.visto_el = ahora
    session.add(sesion)
    session.commit()
    return usuario


def cerrar(session: Session, token: str) -> None:
    sesion = session.exec(select(Sesion).where(Sesion.token == token)).first()
    if sesion is not None:
        session.delete(sesion)
        session.commit()


def cerrar_todas(session: Session, usuario_id: int) -> int:
    """Revocar ya: todas las sesiones de un usuario. Devuelve cuántas cerró."""
    sesiones = list(session.exec(select(Sesion).where(Sesion.usuario_id == usuario_id)))
    for sesion in sesiones:
        session.delete(sesion)
    session.commit()
    return len(sesiones)


def poner_cookie(respuesta: Response, token: str, seguro: bool) -> None:
    """`seguro` es False en localhost sobre HTTP; en producción (Fase 13) va True."""
    respuesta.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=seguro,
        samesite="lax",
        max_age=int(ANTIGUEDAD.total_seconds()),
        path="/",
    )


def borrar_cookie(respuesta: Response) -> None:
    respuesta.delete_cookie(COOKIE, path="/")
