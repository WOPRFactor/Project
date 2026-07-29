"""Pone al día el esquema de una base ya existente.

`create_all` crea tablas nuevas pero **no** agrega columnas a las que ya están, así
que una base creada con una versión anterior de la app se rompe al leer un campo
nuevo. Esto compara el modelo contra la tabla real y agrega lo que falte.

Alcance a propósito chico: solo columnas nuevas. Renombrar, borrar o cambiar tipos
pide una migración de verdad (y un backup antes). Si eso hace falta algún día, acá
es donde se ve venir.

Excepción documentada al "solo ORM": un ALTER TABLE no se puede expresar con el
ORM. Los nombres y tipos salen del metadata de SQLModel, nunca de input del
usuario, así que no hay superficie de inyección.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, text
from sqlmodel import SQLModel

log = logging.getLogger("wopr.migraciones")


def poner_al_dia(engine: Engine) -> list[str]:
    """Agrega las columnas que el modelo tiene y la base todavía no. Devuelve qué hizo."""
    aplicadas: list[str] = []
    inspector = inspect(engine)
    tablas_existentes = set(inspector.get_table_names())

    for nombre_tabla, tabla in SQLModel.metadata.tables.items():
        if nombre_tabla not in tablas_existentes:
            continue  # create_all se encarga de las tablas nuevas
        presentes = {c["name"] for c in inspector.get_columns(nombre_tabla)}
        for columna in tabla.columns:
            if columna.name in presentes:
                continue
            sentencia = _alter(nombre_tabla, columna, engine)
            with engine.begin() as conexion:
                conexion.execute(text(sentencia))
            aplicadas.append(f"{nombre_tabla}.{columna.name}")
            log.info("Columna agregada: %s.%s", nombre_tabla, columna.name)

        aplicadas += _crear_indices(engine, tabla, nombre_tabla)

    return aplicadas


def _crear_indices(engine: Engine, tabla, nombre_tabla: str) -> list[str]:
    """Un ALTER TABLE agrega la columna pero no su índice; hay que crearlo aparte."""
    existentes = {i["name"] for i in inspect(engine).get_indexes(nombre_tabla)}
    creados = []
    for indice in tabla.indexes:
        if indice.name in existentes:
            continue
        indice.create(bind=engine)
        creados.append(f"{nombre_tabla}::{indice.name}")
        log.info("Índice creado: %s", indice.name)
    return creados


def _alter(tabla: str, columna, engine: Engine) -> str:
    tipo = columna.type.compile(engine.dialect)
    sentencia = f'ALTER TABLE "{tabla}" ADD COLUMN "{columna.name}" {tipo}'
    if not columna.nullable:
        sentencia += f" NOT NULL DEFAULT {_default(columna)}"
    return sentencia


def _default(columna) -> str:
    """Valor para las filas que ya existen. SQLite lo exige si la columna es NOT NULL."""
    crudo = getattr(columna.default, "arg", None) if columna.default is not None else None
    if crudo is None:
        crudo = "" if "CHAR" in columna.type.compile().upper() else 0
    if isinstance(crudo, str):
        return "'" + crudo.replace("'", "''") + "'"
    if isinstance(crudo, bool):
        return str(int(crudo))
    if isinstance(crudo, (int, float)):
        return str(crudo)
    # Un default callable o de fecha no se puede expresar acá: mejor frenar el
    # arranque con un mensaje claro que truncarlo o reventar con un TypeError.
    raise RuntimeError(
        f"La columna {columna.name} tiene un default {type(crudo).__name__} que este "
        "migrador no sabe expresar: necesita una migración a mano"
    )
