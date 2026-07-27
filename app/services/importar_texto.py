"""Lectura de tareas pegadas como texto indentado.

    Relevamiento
        Entrevistas con el cliente   4
        Informe de brechas   2  @Ariel
    Hito: relevamiento cerrado

La indentación arma el árbol (tabs o espacios, el parser deduce la unidad), el
número al final es la duración en días hábiles, y `@alguien` el responsable.
Una línea que empieza con «Hito:» o cuya duración es 0 se importa como hito.
"""

from __future__ import annotations

import re

from .importar import FilaImportada, Importacion

_VINETA = re.compile(r"^[-*•·—]\s+")
_DURACION = re.compile(r"[\s.·|]+(\d{1,4})\s*(?:d|días|dias)?$", re.IGNORECASE)
_RESPONSABLE = re.compile(r"\s+@([^\s@]{1,40})\s*$")
_ANCHO_TAB = 4


def leer(texto: str) -> Importacion:
    importacion = Importacion(origen="texto pegado")
    crudas = [l for l in texto.splitlines() if l.strip()]
    if not crudas:
        importacion.avisos.append("No pegaste ninguna línea con contenido.")
        return importacion

    sangrias = sorted({_sangria(l) for l in crudas})
    for numero, cruda in enumerate(crudas, start=1):
        fila = _armar_fila(cruda, sangrias, numero, importacion.avisos)
        if fila is not None:
            importacion.filas.append(fila)
    return importacion


def _sangria(linea: str) -> int:
    ancho = 0
    for caracter in linea:
        if caracter == "\t":
            ancho += _ANCHO_TAB
        elif caracter == " ":
            ancho += 1
        else:
            break
    return ancho


def _armar_fila(
    cruda: str, sangrias: list[int], numero: int, avisos: list[str]
) -> FilaImportada | None:
    nivel = sangrias.index(_sangria(cruda))
    resto = _VINETA.sub("", cruda.strip())

    responsable = ""
    coincidencia = _RESPONSABLE.search(resto)
    if coincidencia:
        responsable = coincidencia.group(1)
        resto = resto[: coincidencia.start()].strip()

    duracion = None
    coincidencia = _DURACION.search(resto)
    if coincidencia:
        duracion = int(coincidencia.group(1))
        resto = resto[: coincidencia.start()].strip()

    titulo = resto.strip(" .·|-")
    if not titulo:
        avisos.append(f"Línea {numero}: quedó sin título después de leerla, la salteo")
        return None

    es_hito = duracion == 0 or titulo.lower().startswith("hito:")
    if duracion is None and not es_hito:
        avisos.append(f"Línea {numero} («{titulo[:40]}») no tenía duración: le pongo 1 día")

    return FilaImportada(
        titulo=titulo,
        tipo="hito" if es_hito else "tarea",
        duracion=0 if es_hito else (duracion or 1),
        responsable=responsable,
        nivel=nivel,
    )
