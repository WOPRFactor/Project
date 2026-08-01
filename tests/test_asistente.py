"""El asistente (Fase 29a): solo lectura, avisos claros y ni un byte a la red.

La llamada a Groq se reemplaza por dobles: los tests no dependen de internet,
de la key real ni del humor de la capa gratuita.
"""

import httpx
import pytest
from sqlmodel import Session

from app.schemas import TareaIn
from app.services import arbol as arbol_service
from app.services import asistente
from app.services.asistente import AsistenteNoDisponible

from .test_app import cliente_fixture  # noqa: F401 — fixture `cliente`


@pytest.fixture(autouse=True)
def key_de_prueba(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_de_prueba")


def test_sin_key_avisa_claro(session: Session, proyecto, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(AsistenteNoDisponible) as error:
        asistente.analizar(session, proyecto.id, "analizá")
    assert "GROQ_API_KEY" in str(error.value)


def test_un_proyecto_inexistente_avisa(session: Session):
    with pytest.raises(AsistenteNoDisponible):
        asistente.analizar(session, 9999, "analizá")


def test_el_contexto_lleva_el_cronograma_y_la_pregunta(session: Session, proyecto, monkeypatch):
    arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo="Relevamiento inicial", duracion=5)
    )
    capturado = {}

    def doble(key, mensajes):
        capturado["key"] = key
        capturado["mensajes"] = mensajes
        return "Análisis de prueba."

    monkeypatch.setattr(asistente, "_completar", doble)
    respuesta = asistente.analizar(session, proyecto.id, "¿qué riesgos ves?")

    assert respuesta == "Análisis de prueba."
    assert capturado["key"] == "gsk_de_prueba"
    contenido = capturado["mensajes"][-1]["content"]
    assert "Relevamiento inicial" in contenido  # viaja el cronograma real
    assert "¿qué riesgos ves?" in contenido


class _Respuesta:
    """Doble de httpx.Response: lo justo para _completar."""

    def __init__(self, cuerpo=None, codigo=200):
        self._cuerpo = cuerpo
        self.status_code = codigo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._cuerpo


def test_una_respuesta_malformada_termina_en_aviso(monkeypatch):
    monkeypatch.setattr(
        asistente.httpx, "post", lambda *a, **kw: _Respuesta({"inesperado": True})
    )
    with pytest.raises(AsistenteNoDisponible) as error:
        asistente._completar("gsk_x", [])
    assert "no se entendió" in str(error.value)


def test_una_key_invalida_lo_dice_con_todas_las_letras(monkeypatch):
    monkeypatch.setattr(asistente.httpx, "post", lambda *a, **kw: _Respuesta(codigo=401))
    with pytest.raises(AsistenteNoDisponible) as error:
        asistente._completar("gsk_x", [])
    assert "GROQ_API_KEY" in str(error.value)


def test_el_timeout_no_revienta(monkeypatch):
    def tarda(*a, **kw):
        raise httpx.ReadTimeout("tarde")

    monkeypatch.setattr(asistente.httpx, "post", tarda)
    with pytest.raises(AsistenteNoDisponible) as error:
        asistente._completar("gsk_x", [])
    assert "a tiempo" in str(error.value)


# --- el panel, de punta a punta (con el doble puesto) ---

def test_el_panel_responde_sin_tocar_el_proyecto(cliente, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_de_prueba")
    monkeypatch.setattr(
        asistente, "_completar", lambda key, mensajes: "Todo en orden, capo."
    )
    cliente.post(
        "/proyectos",
        data={"nombre": "Con asistente", "descripcion": "", "fecha_inicio": "2026-01-05"},
        follow_redirects=True,
    )
    cliente.post("/proyectos/1/tareas/agregar")

    respuesta = cliente.post("/proyectos/1/asistente", data={"pregunta": "¿cómo viene?"})
    assert respuesta.status_code == 200
    assert "Todo en orden, capo." in respuesta.text

    # Solo lectura: la grilla sigue con su única tarea, nada se creó ni cambió.
    tablero = cliente.get("/proyectos/1")
    assert tablero.text.count('name="titulo"') == 1


def test_el_panel_muestra_el_aviso_cuando_no_hay_key(cliente, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cliente.post(
        "/proyectos",
        data={"nombre": "Sin key", "descripcion": "", "fecha_inicio": "2026-01-05"},
        follow_redirects=True,
    )
    respuesta = cliente.post("/proyectos/1/asistente", data={"pregunta": "hola"})
    assert respuesta.status_code == 200
    assert "GROQ_API_KEY" in respuesta.text
