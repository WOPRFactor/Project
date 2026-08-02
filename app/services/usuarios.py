"""Cuentas: alta por el admin, login con throttling y cambio de contraseña.

Reglas que se cuidan acá:

- **El mensaje de credenciales inválidas es único.** No distingue "no existe ese
  mail" de "contraseña incorrecta": la diferencia le regalaría a un atacante la
  lista de cuentas válidas.
- **Throttling progresivo por cuenta.** Cada intento fallido suma espera; un
  login exitoso la borra. Es en memoria a propósito: con un proceso alcanza, y
  reiniciar la app no es un ataque.
- **El hash nunca sale de este módulo.** Ni a un log, ni a una respuesta.
"""

from __future__ import annotations

import re
import time

from sqlmodel import Session, select

from ..auth import hash as hash_service
from ..auth import sesion as sesion_service
from ..models_auth import Usuario

_MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Espera en segundos según cuántos fallos acumulados lleva la cuenta.
_ESPERAS = [0, 0, 1, 3, 10, 30, 60]
_fallos: dict[str, tuple[int, float]] = {}


class CuentaInvalida(Exception):
    """Alta o cambio rechazado; el mensaje se le muestra al usuario."""


class CredencialesInvalidas(Exception):
    """Login fallido. Mensaje único a propósito."""

    def __init__(self, espera: int = 0) -> None:
        self.espera = espera
        if espera:
            super().__init__(
                f"Mail o contraseña incorrectos. Esperá {espera} segundos antes de reintentar."
            )
        else:
            super().__init__("Mail o contraseña incorrectos")


def normalizar_mail(mail: str) -> str:
    return mail.strip().lower()[:160]


def listar(session: Session) -> list[Usuario]:
    usuarios = list(session.exec(select(Usuario)))
    usuarios.sort(key=lambda u: (not u.es_admin, u.mail))
    return usuarios


def obtener(session: Session, usuario_id: int) -> Usuario | None:
    return session.get(Usuario, usuario_id)


def por_mail(session: Session, mail: str) -> Usuario | None:
    clave = normalizar_mail(mail)
    if not clave:
        return None
    return session.exec(select(Usuario).where(Usuario.mail == clave)).first()


def hay_alguno(session: Session) -> bool:
    """Si no hay ninguna cuenta, la app ofrece crear el primer admin."""
    return session.exec(select(Usuario)).first() is not None


def crear(
    session: Session,
    mail: str,
    password: str,
    nombre: str = "",
    es_admin: bool = False,
    debe_cambiar: bool = True,
) -> Usuario:
    """Alta de cuenta. Solo la usa el admin (o el arranque del primer usuario)."""
    clave = normalizar_mail(mail)
    if not _MAIL.match(clave):
        raise CuentaInvalida("Ese mail no tiene una forma válida")
    if por_mail(session, clave) is not None:
        raise CuentaInvalida(f"Ya existe una cuenta con el mail {clave}")
    problema = hash_service.validar_fuerza(password)
    if problema:
        raise CuentaInvalida(problema)

    usuario = Usuario(
        mail=clave,
        nombre=nombre.strip()[:120],
        hash_password=hash_service.hashear(password),
        es_admin=es_admin,
        debe_cambiar_password=debe_cambiar,
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


def autenticar(session: Session, mail: str, password: str) -> Usuario:
    """Devuelve el usuario o levanta CredencialesInvalidas. Aplica throttling."""
    clave = normalizar_mail(mail)
    espera = _espera_pendiente(clave)
    if espera:
        raise CredencialesInvalidas(espera)

    usuario = por_mail(session, clave)
    if usuario is None or not usuario.activo:
        _anotar_fallo(clave)
        raise CredencialesInvalidas()
    if not hash_service.verificar(usuario.hash_password, password):
        _anotar_fallo(clave)
        raise CredencialesInvalidas()

    _fallos.pop(clave, None)
    if hash_service.necesita_rehash(usuario.hash_password):
        usuario.hash_password = hash_service.hashear(password)
        session.add(usuario)
        session.commit()
        session.refresh(usuario)
    return usuario


def cambiar_password(
    session: Session, usuario: Usuario, actual: str, nueva: str, repetida: str
) -> None:
    """Cambio propio: exige la actual, salvo que sea la de un solo uso del alta."""
    if nueva != repetida:
        raise CuentaInvalida("Las dos contraseñas nuevas no coinciden")
    problema = hash_service.validar_fuerza(nueva)
    if problema:
        raise CuentaInvalida(problema)
    if not hash_service.verificar(usuario.hash_password, actual):
        raise CuentaInvalida("La contraseña actual no es correcta")
    if nueva == actual:
        raise CuentaInvalida("La contraseña nueva tiene que ser distinta de la actual")

    usuario.hash_password = hash_service.hashear(nueva)
    usuario.debe_cambiar_password = False
    session.add(usuario)
    session.commit()
    # Cambiar la contraseña cierra las otras sesiones: si alguien te la robó, se va.
    sesion_service.cerrar_todas(session, usuario.id or 0)


def resetear_password(session: Session, usuario_id: int, nueva: str) -> Usuario:
    """El admin entrega una contraseña de un solo uso; el dueño la cambia al entrar."""
    usuario = session.get(Usuario, usuario_id)
    if usuario is None:
        raise CuentaInvalida("Esa cuenta no existe")
    problema = hash_service.validar_fuerza(nueva)
    if problema:
        raise CuentaInvalida(problema)

    usuario.hash_password = hash_service.hashear(nueva)
    usuario.debe_cambiar_password = True
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    sesion_service.cerrar_todas(session, usuario_id)
    return usuario


def cambiar_activo(session: Session, usuario_id: int, activo: bool) -> Usuario:
    """Desactivar corta el acceso ya: además de bloquear el login, cierra sesiones."""
    usuario = session.get(Usuario, usuario_id)
    if usuario is None:
        raise CuentaInvalida("Esa cuenta no existe")
    if not activo and usuario.es_admin and _admins_activos(session) <= 1:
        raise CuentaInvalida("No podés desactivar al último admin activo")

    usuario.activo = activo
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    if not activo:
        sesion_service.cerrar_todas(session, usuario_id)
    return usuario


def _admins_activos(session: Session) -> int:
    return len([u for u in session.exec(select(Usuario)) if u.es_admin and u.activo])


def _espera_pendiente(clave: str) -> int:
    intentos, ultimo = _fallos.get(clave, (0, 0.0))
    if not intentos:
        return 0
    espera = _ESPERAS[min(intentos, len(_ESPERAS) - 1)]
    restante = espera - (time.monotonic() - ultimo)
    return max(0, int(restante + 0.999))


def _anotar_fallo(clave: str) -> None:
    intentos, _ = _fallos.get(clave, (0, 0.0))
    _fallos[clave] = (intentos + 1, time.monotonic())


def olvidar_intentos() -> None:
    """Para los tests: borra el throttling acumulado."""
    _fallos.clear()
