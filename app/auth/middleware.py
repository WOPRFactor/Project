"""El CSRF se exige acá, para todas las rutas mutantes a la vez.

Ponerlo en cada router sería confiar en que nadie se olvide al agregar una ruta
nueva; en el middleware, una ruta nueva nace protegida. Los GET no pasan por el
chequeo (no mutan), y las rutas públicas de login están exentas porque todavía no
hay sesión de la cual derivar el token.

El token llega de dos formas: por cabecera (lo pone `grilla.js` en cada pedido
HTMX) o como campo oculto en los formularios HTML comunes. Para leer el campo hay
que leer el body **sin consumirlo**: el endpoint todavía tiene que poder parsearlo,
así que se vuelve a poner en el stream antes de seguir.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

# Sin sesión no hay token CSRF posible: estas rutas se defienden con SameSite=Lax
# en la cookie y con el throttling del login.
_EXENTAS = {"/ingresar", "/primer-usuario"}
_SEGUROS = {"GET", "HEAD", "OPTIONS"}
_FORMULARIO = "application/x-www-form-urlencoded"

from . import csrf, sesion  # noqa: E402


class ExigeCsrf(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _SEGUROS or request.url.path in _EXENTAS:
            return await call_next(request)

        token_sesion = request.cookies.get(sesion.COOKIE, "")
        if not token_sesion:
            # Sin sesión, la ruta va a rebotar igual por falta de autenticación.
            return await call_next(request)

        recibido = request.headers.get(csrf.CABECERA, "")
        if not recibido and request.headers.get("content-type", "").startswith(_FORMULARIO):
            recibido = await _token_del_cuerpo(request)

        if not csrf.es_valido(token_sesion, recibido):
            return PlainTextResponse(
                "Tu sesión cambió o el formulario venció. Recargá la página y probá de nuevo.",
                status_code=403,
            )
        return await call_next(request)


async def _token_del_cuerpo(request: Request) -> str:
    """Lee el campo oculto y **repone el body** para que el endpoint lo lea igual."""
    cuerpo = await request.body()

    async def repetir():
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    request._receive = repetir  # noqa: SLF001 — la única forma de rebobinar el stream
    campos = parse_qs(cuerpo.decode("utf-8", "replace"))
    return (campos.get(csrf.CAMPO) or [""])[0]
