"""Token CSRF: un secreto por sesión que todo verbo que no sea GET tiene que traer.

Con cookies, cualquier página de internet puede hacer que tu navegador dispare un
POST a la app con tus credenciales adjuntas. El token corta eso: viaja en el HTML
(que solo puede leer el mismo origen) y se exige en cada mutación.

Va derivado del token de sesión con HMAC y `SECRET_KEY`: no necesita otra tabla ni
estado en memoria, y muere junto con la sesión. Comparación en tiempo constante.
"""

from __future__ import annotations

import hashlib
import hmac

from ..config import secret_key

CAMPO = "csrf_token"
CABECERA = "x-csrf-token"


def token_de(token_sesion: str) -> str:
    """El token CSRF que le corresponde a esta sesión. Vacío si no hay sesión."""
    if not token_sesion:
        return ""
    return hmac.new(
        secret_key().encode(), token_sesion.encode(), hashlib.sha256
    ).hexdigest()


def es_valido(token_sesion: str, recibido: str) -> bool:
    esperado = token_de(token_sesion)
    if not esperado or not recibido:
        return False
    return hmac.compare_digest(esperado, recibido)
