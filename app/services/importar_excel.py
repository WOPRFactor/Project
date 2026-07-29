"""Lectura de planillas tipo Gantt (WBS · Tarea · Resp. · Predec. · Días · _tipo).

Dos rarezas del mundo real que este parser resuelve y **reporta**:

1. Excel convierte un WBS como `4.6` en la fecha 2026-06-04. La conversión es
   reversible sin ambigüedad (día.mes reconstruye el código), así que se repara.
2. Filas sin WBS o con predecesoras a códigos inexistentes: se importan igual,
   con aviso, en vez de perder el dato.
"""

from __future__ import annotations

import datetime
from io import BytesIO

from openpyxl import load_workbook

from .importar import AMBITOS, MAX_FILAS, TIPOS, FilaImportada, Importacion

# El tope real de tareas más un margen para la cabecera (está en las primeras 15
# filas). Antes se cortaba en 400 en silencio, muy por debajo de MAX_FILAS.
_MAX_LEER = MAX_FILAS + 20

_COLUMNAS = {
    "wbs": "wbs",
    "tarea": "titulo",
    "resp": "responsable",
    "resp.": "responsable",
    "responsable": "responsable",
    "predec": "predecesoras",
    "predec.": "predecesoras",
    "predecesoras": "predecesoras",
    "dias": "duracion",
    "días": "duracion",
    "crit": "critica",
    "crit.": "critica",
    "crít": "critica",
    "crít.": "critica",
    "critica": "critica",
    "crítica": "critica",
    "criticidad": "critica",
    "ambito": "ambito",
    "ámbito": "ambito",
    "peso": "peso",
    "opt": "optimista",
    "optimista": "optimista",
    "pes": "pesimista",
    "pesimista": "pesimista",
    "_tipo": "tipo",
    "tipo": "tipo",
    "inicio": "inicio",
    "comienzo": "inicio",
    "fin": "fin",
    "final": "fin",
    "termino": "fin",
    "término": "fin",
}
_AFIRMATIVOS = {"si", "sí", "s", "yes", "y", "true", "verdadero", "x", "1"}
_VACIAS_SEGUIDAS = 15


def hojas(contenido: bytes) -> list[str]:
    libro = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    try:
        return list(libro.sheetnames)
    finally:
        libro.close()


def leer(contenido: bytes, hoja: str | None = None) -> Importacion:
    """Filas importables de la hoja pedida.

    Sin hoja explícita, se elige la primera que tenga las columnas esperadas: un
    libro suele traer hojas de notas o de ayuda, y agarrar una de esas por posición
    daría "no encontré tareas" sobre un archivo perfectamente válido.
    """
    libro = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    try:
        candidatas = [libro[hoja]] if hoja and hoja in libro.sheetnames else libro.worksheets
        elegida, filas_crudas, mapa, primera = _elegir_hoja(candidatas)
    finally:
        libro.close()

    importacion = Importacion(origen=f"planilla · hoja «{elegida}»")
    if mapa is None:
        importacion.avisos.append(
            "No encontré la fila de encabezados: la planilla necesita columnas "
            "«WBS» y «Tarea»."
        )
        return importacion
    if len(filas_crudas) >= _MAX_LEER:
        importacion.avisos.append(
            f"La hoja tiene más de {MAX_FILAS} filas: leí hasta ahí y el resto no entró"
        )

    vacias = 0
    vio_wbs = False
    for numero, cruda in enumerate(filas_crudas[primera:], start=primera + 1):
        celdas = {campo: cruda[i] for campo, i in mapa.items() if i < len(cruda)}
        titulo = _texto(celdas.get("titulo"))
        if not titulo:
            # Una fila en blanco después de la tabla numerada marca el final: lo que
            # sigue suele ser la leyenda de la planilla, no tareas.
            if vio_wbs and not any(_texto(v) for v in cruda):
                break
            vacias += 1
            if vacias >= _VACIAS_SEGUIDAS:
                break
            continue
        vacias = 0
        fila = _armar_fila(celdas, titulo, numero, importacion.avisos)
        if fila is not None:
            vio_wbs = vio_wbs or bool(fila.wbs)
            importacion.filas.append(fila)

    return importacion


def _elegir_hoja(candidatas) -> tuple[str, list[list], dict[str, int] | None, int]:
    """La **última** hoja con cabecera válida.

    Se recorre de derecha a izquierda porque la versión vigente de un plan suele
    ser la hoja más a la derecha; pero se saltean las que no tienen las columnas
    (notas, ayuda, glosario), que si no ganarían solo por estar últimas.
    """
    ultima = None
    for ws in reversed(list(candidatas)):
        filas = [list(f) for f in ws.iter_rows(max_row=_MAX_LEER, max_col=20, values_only=True)]
        mapa, desde = _ubicar_cabecera(filas)
        if mapa is not None:
            return ws.title, filas, mapa, desde
        if ultima is None:
            ultima = (ws.title, filas)
    titulo, filas = ultima or ("(vacía)", [])
    return titulo, filas, None, 0


def _ubicar_cabecera(filas: list[list]) -> tuple[dict[str, int] | None, int]:
    for indice, cruda in enumerate(filas[:15]):
        etiquetas = {_texto(v).lower(): i for i, v in enumerate(cruda) if _texto(v)}
        mapa = {_COLUMNAS[k]: i for k, i in etiquetas.items() if k in _COLUMNAS}
        if "wbs" in mapa and "titulo" in mapa:
            return mapa, indice + 1
    return None, 0


def _armar_fila(
    celdas: dict, titulo: str, numero: int, avisos: list[str]
) -> FilaImportada | None:
    tipo = _texto(celdas.get("tipo")).lower()
    wbs = _codigo(celdas.get("wbs"), numero, "WBS", avisos)
    if tipo not in TIPOS:
        tipo = "fase" if wbs and "." not in wbs and not _numero(celdas.get("duracion")) else "tarea"

    duracion = _numero(celdas.get("duracion"))
    predecesoras = _predecesoras(celdas.get("predecesoras"), numero, avisos)

    if not wbs:
        avisos.append(
            f"Fila {numero} («{titulo[:40]}») no tiene WBS: la importo en el primer nivel"
        )

    return FilaImportada(
        titulo=titulo,
        wbs=wbs,
        tipo=tipo,
        duracion=0 if tipo == "hito" else max(int(duracion or 1), 1),
        responsable=_texto(celdas.get("responsable")),
        critica=_texto(celdas.get("critica")).lower() in _AFIRMATIVOS,
        ambito=_ambito(_texto(celdas.get("ambito"))),
        peso=_numero(celdas.get("peso")),
        duracion_optimista=_numero(celdas.get("optimista")),
        duracion_pesimista=_numero(celdas.get("pesimista")),
        predecesoras=predecesoras,
        inicio_declarado=_fecha(celdas.get("inicio")),
        fin_declarado=_fecha(celdas.get("fin")),
        nivel=wbs.count(".") if wbs else 0,
    )


def _ambito(texto: str) -> str:
    """La planilla puede traer la etiqueta con mayúscula; el enum es cerrado igual."""
    limpio = texto.strip().lower()
    return limpio if limpio in AMBITOS else "proyecto"


def _predecesoras(valor, numero: int, avisos: list[str]) -> list[str]:
    if isinstance(valor, datetime.datetime | datetime.date):
        return [_codigo(valor, numero, "una predecesora", avisos)]
    return [c.strip() for c in _texto(valor).split(",") if c.strip()]


def _codigo(valor, numero: int, campo: str, avisos: list[str]) -> str:
    """Recupera un WBS que Excel haya convertido en fecha (`4.6` → 2026-06-04)."""
    if isinstance(valor, datetime.datetime | datetime.date):
        recuperado = f"{valor.day}.{valor.month}"
        avisos.append(
            f"Fila {numero}: Excel había convertido {campo} en la fecha "
            f"{valor.strftime('%d/%m/%Y')}; lo interpreto como {recuperado}"
        )
        return recuperado
    texto = _texto(valor)
    return texto.rstrip(".") if texto else ""


def _fecha(valor) -> datetime.date | None:
    """Solo se usa para diagnosticar; nunca para fijar el cronograma."""
    if isinstance(valor, datetime.datetime):
        return valor.date()
    return valor if isinstance(valor, datetime.date) else None


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _numero(valor) -> int | None:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None
