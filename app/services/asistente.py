"""Asistente con IA: análisis y recomendaciones sobre el cronograma (Fase 29a).

**Solo lectura**: este service no escribe nada en la base. El contexto que viaja
a Groq es el export markdown — el mismo dato que ya sale de la app por
`export.a_markdown` — así el asistente nunca ve algo distinto de la pantalla.
Sin GROQ_API_KEY, sin red o con una respuesta rota, se avisa con un mensaje
claro; jamás un 500.
"""

from __future__ import annotations

import httpx
from sqlmodel import Session

from ..config import groq_api_key, ia_modelo
from . import export as export_service

_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT = 30.0
_MAX_PREGUNTA = 2000

_INSTRUCCIONES = """Sos un project manager senior que asesora al dueño de un \
proyecto. Te llega el cronograma en markdown: árbol de tareas con fechas \
calculadas, duraciones en días hábiles, tareas críticas marcadas y las \
dependencias al final. Respondés en castellano rioplatense, conciso y \
accionable: qué está bien, qué riesgos ves (cadenas largas de dependencias, \
tareas críticas, hitos comprometidos, etapas desbalanceadas) y qué harías \
distinto. No inventes datos que no estén en el cronograma. Respondé en texto \
plano, sin formato markdown."""


class AsistenteNoDisponible(Exception):
    """El análisis no se pudo hacer; el mensaje se le muestra al usuario."""


def analizar(session: Session, project_id: int, pregunta: str) -> str:
    """Análisis del proyecto en texto. Lanza AsistenteNoDisponible con mensaje claro."""
    key = groq_api_key()
    if not key:
        raise AsistenteNoDisponible(
            "Falta la GROQ_API_KEY: cargala en el archivo .env de la raíz "
            "(la key se crea gratis en console.groq.com)"
        )

    contexto = export_service.a_markdown(session, project_id)
    if contexto is None:
        raise AsistenteNoDisponible("Ese proyecto no existe")

    pedido = pregunta.strip()[:_MAX_PREGUNTA] or (
        "Analizá el proyecto y dame recomendaciones."
    )
    mensajes = [
        {"role": "system", "content": _INSTRUCCIONES},
        {
            "role": "user",
            "content": f"Cronograma del proyecto:\n\n{contexto}\n\nPedido: {pedido}",
        },
    ]
    return _completar(key, mensajes)


def _completar(key: str, mensajes: list[dict]) -> str:
    """La llamada a Groq, aislada para que los tests la reemplacen por un doble."""
    try:
        respuesta = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": ia_modelo(), "messages": mensajes, "temperature": 0.3},
            timeout=_TIMEOUT,
        )
        respuesta.raise_for_status()
        texto = respuesta.json()["choices"][0]["message"]["content"]
    except httpx.TimeoutException as error:
        raise AsistenteNoDisponible(
            "Groq no respondió a tiempo; probá de nuevo en un momento"
        ) from error
    except httpx.HTTPStatusError as error:
        raise AsistenteNoDisponible(_mensaje_http(error.response.status_code)) from error
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
        raise AsistenteNoDisponible("La respuesta de Groq no se entendió") from error

    if not isinstance(texto, str) or not texto.strip():
        raise AsistenteNoDisponible("Groq devolvió una respuesta vacía")
    return texto.strip()


def _mensaje_http(codigo: int) -> str:
    if codigo == 401:
        return "La GROQ_API_KEY no es válida: revisala en el .env"
    if codigo == 429:
        return "Groq está limitando los pedidos (capa gratuita): esperá un momento"
    if codigo == 404:
        return "El modelo configurado no existe en Groq: revisá WOPR_IA_MODELO"
    if codigo >= 500:
        return "Groq está con problemas; probá más tarde"
    return f"Groq rechazó el pedido (HTTP {codigo})"
