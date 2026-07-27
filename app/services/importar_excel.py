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

from .importar import TIPOS, FilaImportada, Importacion

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
    "_tipo": "tipo",
    "tipo": "tipo",
}
_VACIAS_SEGUIDAS = 15


def hojas(contenido: bytes) -> list[str]:
    libro = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    try:
        return list(libro.sheetnames)
    finally:
        libro.close()


def leer(contenido: bytes, hoja: str | None = None) -> Importacion:
    """Devuelve las filas importables de la hoja pedida (por default, la última)."""
    libro = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    try:
        ws = libro[hoja] if hoja and hoja in libro.sheetnames else libro.worksheets[-1]
        filas_crudas = [list(f) for f in ws.iter_rows(max_row=400, max_col=20, values_only=True)]
    finally:
        libro.close()

    importacion = Importacion(origen=f"planilla · hoja «{ws.title}»")
    mapa, primera = _ubicar_cabecera(filas_crudas)
    if mapa is None:
        importacion.avisos.append(
            "No encontré la fila de encabezados: la planilla necesita columnas "
            "«WBS» y «Tarea»."
        )
        return importacion

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
        predecesoras=predecesoras,
        nivel=wbs.count(".") if wbs else 0,
    )


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
