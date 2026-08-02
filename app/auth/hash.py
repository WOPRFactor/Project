"""Hash de contraseñas con argon2id. El único lugar del repo que las toca.

argon2id y no bcrypt/sha: es el algoritmo recomendado hoy y el que resiste
ataques con GPU. Los parámetros son los del preset de `argon2-cffi`, que la
librería mantiene al día — mejor eso que números elegidos a mano acá.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

MINIMO = 10


def hashear(password: str) -> str:
    return _hasher.hash(password)


def verificar(hash_guardado: str, password: str) -> bool:
    """True si la contraseña coincide. Nunca propaga la excepción de la librería."""
    try:
        return _hasher.verify(hash_guardado, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_guardado: str) -> bool:
    """El día que suban los parámetros, un login exitoso puede re-hashear."""
    try:
        return _hasher.check_needs_rehash(hash_guardado)
    except InvalidHashError:
        return False


def validar_fuerza(password: str) -> str | None:
    """Devuelve el problema, o None si sirve. Mínimo honesto, sin teatro de reglas."""
    if len(password) < MINIMO:
        return f"La contraseña necesita al menos {MINIMO} caracteres"
    if password.strip() != password:
        return "La contraseña no puede empezar ni terminar con espacios"
    return None
