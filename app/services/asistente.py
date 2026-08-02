"""Asistente con IA: análisis, recomendaciones y acciones propuestas (Fase 29).

Este service **no escribe nada** en la base: devuelve análisis en texto y, si el
pedido implica cambios, acciones *propuestas* (el contrato cerrado de
`asistente_acciones`) que el usuario confirma aparte. El contexto que viaja a
Groq es el export markdown — el mismo dato que ya sale de la app — más los
códigos WBS, que son como el modelo referencia tareas. Sin GROQ_API_KEY, sin
red o con una respuesta rota, se avisa con un mensaje claro; jamás un 500.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
from sqlmodel import Session

from ..config import groq_api_key, ia_modelo
from . import asistente_acciones
from . import export as export_service
from . import tasks as tasks_service

_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT = 45.0
_MAX_PREGUNTA = 2000

_INSTRUCCIONES = """Sos un project manager senior que asesora al dueño de un \
proyecto. Te llega el cronograma en markdown (árbol de tareas con fechas \
calculadas y duraciones en días hábiles) más el listado de códigos WBS. \
Respondés SIEMPRE con un JSON válido con esta forma exacta:
{"analisis": "tu análisis en texto plano, castellano rioplatense, conciso y accionable", "acciones": []}

Si el pedido implica cambios al cronograma, proponelos en "acciones" (máximo 20). \
Tipos permitidos, y ninguno más:
- {"tipo": "crear_tarea", "titulo": "...", "padre_wbs": "código WBS de la etapa o '' para primer nivel", "duracion": entero en días hábiles (0 = hito), "predecesoras": "códigos WBS, ej. '1.3' o '1.3+2, 2.1SS'", "critica": true|false}
- {"tipo": "modificar_tarea", "wbs": "...", "titulo": "...o null", "duracion": entero o null, "critica": true|false|null}
- {"tipo": "cambiar_predecesoras", "wbs": "...", "predecesoras": "la lista COMPLETA que queda; '' las borra todas"}

Las acciones son propuestas: el usuario las revisa antes de aplicar. Si el \
pedido es solo análisis o consulta, "acciones" queda vacío. Referenciá tareas \
siempre por su código WBS del listado. No inventes datos ni códigos."""


class AsistenteNoDisponible(Exception):
    """La consulta no se pudo hacer; el mensaje se le muestra al usuario."""


@dataclass
class Consulta:
    """Lo que vuelve del asistente: análisis siempre, acciones solo si las propuso."""

    analisis: str
    acciones: list = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def consultar(session: Session, project_id: int, pregunta: str) -> Consulta:
    """Análisis (y acciones propuestas) del proyecto. Lanza AsistenteNoDisponible."""
    key = groq_api_key()
    if not key:
        raise AsistenteNoDisponible(
            "Falta la GROQ_API_KEY: cargala en el archivo .env de la raíz "
            "(la key se crea gratis en console.groq.com)"
        )

    contexto = _contexto(session, project_id)
    if contexto is None:
        raise AsistenteNoDisponible("Ese proyecto no existe")

    pedido = pregunta.strip()[:_MAX_PREGUNTA] or (
        "Analizá el proyecto y dame recomendaciones."
    )
    mensajes = [
        {"role": "system", "content": _INSTRUCCIONES},
        {"role": "user", "content": f"{contexto}\n\nPedido: {pedido}"},
    ]
    return _interpretar(_completar(key, mensajes))


def _contexto(session: Session, project_id: int) -> str | None:
    """El cronograma como lo exporta la app, más los códigos WBS para referenciar."""
    cronograma = export_service.a_markdown(session, project_id)
    if cronograma is None:
        return None
    codigos = [
        f"- {tarea.codigo or '(sin código)'} — {tarea.titulo}"
        for tarea, _ in tasks_service.arbol(session, project_id)
    ]
    listado = "\n".join(codigos) or "_Sin tareas._"
    return f"Cronograma del proyecto:\n\n{cronograma}\n## Códigos WBS\n\n{listado}"


def _interpretar(crudo: str) -> Consulta:
    """El JSON del modelo, con red de contención: si viene roto, es solo análisis."""
    try:
        datos = json.loads(crudo)
        analisis = str(datos.get("analisis", "")).strip()
        acciones, avisos = asistente_acciones.parsear(datos.get("acciones", []))
    except (json.JSONDecodeError, AttributeError, TypeError):
        # Texto plano en vez del JSON pedido: se muestra igual, sin acciones.
        return Consulta(analisis=crudo)
    if not analisis:
        analisis = "(el asistente no devolvió análisis)"
    return Consulta(analisis=analisis, acciones=acciones, avisos=avisos)


def _completar(key: str, mensajes: list[dict]) -> str:
    """La llamada a Groq, aislada para que los tests la reemplacen por un doble."""
    try:
        respuesta = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": ia_modelo(),
                "messages": mensajes,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
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
