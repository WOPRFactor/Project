"""Export del proyecto a JSON (backup portable) y a Markdown (legible).

Los dos salen del mismo cronograma calculado, así el export nunca muestra fechas
distintas a las de la pantalla.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from sqlmodel import Session

from ..models import Project
from . import dependencies as dependencies_service
from . import projects as projects_service
from . import vista as vista_service

_NO_ALFANUMERICO = re.compile(r"[^a-z0-9]+")


def nombre_de_archivo(proyecto: Project, extension: str) -> str:
    """Slug ASCII seguro para la cabecera Content-Disposition.

    Se descarta todo lo que no sea alfanumérico: así el nombre del proyecto —que es
    input del usuario— no puede inyectar comillas ni saltos de línea en la cabecera.
    """
    sin_acentos = unicodedata.normalize("NFKD", proyecto.nombre).encode("ascii", "ignore")
    base = _NO_ALFANUMERICO.sub("-", sin_acentos.decode().lower()).strip("-")
    return f"{base or 'proyecto'}.{extension}"


def a_json(session: Session, project_id: int) -> dict | None:
    """Dump completo: estructura, fechas calculadas y dependencias."""
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return None

    datos = vista_service.armar(session, project_id)
    por_id = {f.tarea.id: f.tarea.titulo for f in datos.filas}

    return {
        "exportado": date.today().isoformat(),
        "proyecto": {
            "nombre": proyecto.nombre,
            "descripcion": proyecto.descripcion,
            "fecha_inicio": proyecto.fecha_inicio.isoformat(),
            "estado": proyecto.estado.value,
        },
        "error_de_calculo": datos.error,
        "tareas": [
            {
                "id": fila.tarea.id,
                "titulo": fila.tarea.titulo,
                "notas": fila.tarea.notas,
                "parent_id": fila.tarea.parent_id,
                "nivel": fila.nivel,
                "es_resumen": fila.es_resumen,
                "duracion_dias_habiles": None if fila.es_resumen else fila.tarea.duracion,
                "no_antes_de": fila.tarea.snet.isoformat() if fila.tarea.snet else None,
                "estado": fila.estado.nombre if fila.estado else None,
                "terminada": vista_service.esta_hecha(fila),
                "inicio": fila.inicio.isoformat() if fila.inicio else None,
                "fin": fila.fin.isoformat() if fila.fin else None,
                "responsable": fila.tarea.responsable,
                # Dos cosas distintas: la criticidad la marca el usuario, la holgura
                # sale del grafo. Se exportan por separado a propósito.
                "critica_para_el_negocio": fila.tarea.critica,
                "holgura_dias": fila.holgura,
                "sin_margen": fila.sin_holgura,
            }
            for fila in datos.filas
        ],
        "dependencias": [
            {
                "predecesora_id": dep.predecessor_id,
                "predecesora": por_id.get(dep.predecessor_id),
                "sucesora_id": dep.successor_id,
                "sucesora": por_id.get(dep.successor_id),
                "lag_dias_habiles": dep.lag,
            }
            for dep in dependencies_service.listar(session, project_id)
        ],
    }


def a_markdown(session: Session, project_id: int) -> str | None:
    """Un `.md` legible: árbol indentado con fechas, y las dependencias al final."""
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return None

    datos = vista_service.armar(session, project_id)
    por_id = {f.tarea.id: f.tarea.titulo for f in datos.filas}
    lineas = [f"# {proyecto.nombre}", ""]

    if proyecto.descripcion:
        lineas += [proyecto.descripcion, ""]
    lineas.append(f"- **Inicio del proyecto:** {_fecha(proyecto.fecha_inicio)}")
    if datos.filas:
        fines = [f.fin for f in datos.filas if f.fin]
        if fines:
            lineas.append(f"- **Fin calculado:** {_fecha(max(fines))}")
    lineas += [f"- **Estado:** {proyecto.estado.value}", ""]

    if datos.error:
        lineas += [f"> El cronograma no se pudo calcular: {datos.error}", ""]

    lineas += ["## Tareas", ""]
    if not datos.filas:
        lineas.append("_Sin tareas cargadas._")
    for fila in datos.filas:
        lineas.append(_linea_de_tarea(fila))

    dependencias = dependencies_service.listar(session, project_id)
    if dependencias:
        lineas += ["", "## Dependencias", ""]
        for dep in dependencias:
            predecesora = por_id.get(dep.predecessor_id, "?")
            sucesora = por_id.get(dep.successor_id, "?")
            lineas.append(f"- **{sucesora}** arranca cuando termina **{predecesora}**{_lag(dep.lag)}")

    return "\n".join(lineas) + "\n"


def _linea_de_tarea(fila: vista_service.Fila) -> str:
    sangria = "  " * fila.nivel
    marca = "~~" if vista_service.esta_hecha(fila) else ""
    titulo = f"{marca}{fila.tarea.titulo}{marca}"
    if fila.es_resumen:
        titulo = f"**{titulo}**"

    detalle = [f"{_fecha(fila.inicio)} → {_fecha(fila.fin)}"]
    if not fila.es_resumen:
        detalle.append(f"{fila.tarea.duracion}d")
        if fila.tarea.critica:
            detalle.append("crítica")
        if fila.tarea.responsable:
            detalle.append(fila.tarea.responsable)
    if fila.estado is not None:
        detalle.append(fila.estado.nombre.lower())
    return f"{sangria}- {titulo} — {' · '.join(detalle)}"


def _lag(lag: int) -> str:
    if lag > 0:
        return f", más {lag} días hábiles"
    if lag < 0:
        return f", con {-lag} días hábiles de solape"
    return ""


def _fecha(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"
