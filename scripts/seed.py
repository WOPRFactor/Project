"""Carga un proyecto de ejemplo con subtareas y dependencias.

    uv run python scripts/seed.py

Sirve para ver el timeline con datos reales sin cargar nada a mano.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.schemas import DependenciaIn, ProyectoIn, TareaIn  # noqa: E402
from app.services import dependencies as dependencies_service  # noqa: E402
from app.services import projects as projects_service  # noqa: E402
from app.services import tasks as tasks_service  # noqa: E402

ESTRUCTURA = [
    ("Relevamiento", None, 0, [
        ("Entrevistas con el cliente", 4),
        ("Inventario de activos", 3),
        ("Informe de brechas", 2),
    ]),
    ("Diseño", None, 0, [
        ("Arquitectura objetivo", 5),
        ("Plan de controles", 3),
    ]),
    ("Implementación", None, 0, [
        ("Hardening de servidores", 8),
        ("Despliegue de EDR", 6),
        ("Capacitación al equipo", 2),
    ]),
    ("Cierre", None, 0, [
        ("Pentest de validación", 5),
        ("Informe ejecutivo", 3),
    ]),
]

VINCULOS = [
    ("Entrevistas con el cliente", "Inventario de activos", 0),
    ("Inventario de activos", "Informe de brechas", 0),
    ("Informe de brechas", "Arquitectura objetivo", 0),
    ("Arquitectura objetivo", "Plan de controles", -2),
    ("Plan de controles", "Hardening de servidores", 0),
    ("Plan de controles", "Despliegue de EDR", 3),
    ("Hardening de servidores", "Pentest de validación", 0),
    ("Despliegue de EDR", "Pentest de validación", 0),
    ("Pentest de validación", "Informe ejecutivo", 0),
]


def main() -> None:
    init_db()
    with Session(engine) as session:
        proyecto = projects_service.crear(
            session,
            ProyectoIn(
                nombre="Implementación ISO 27001 — Cliente demo",
                descripcion="Proyecto de ejemplo para ver el timeline con datos reales",
                fecha_inicio=date(2026, 8, 3),
            ),
        )

        por_titulo = {}
        for titulo, _, _, hijas in ESTRUCTURA:
            padre = tasks_service.crear(session, proyecto.id, TareaIn(titulo=titulo))
            for titulo_hija, duracion in hijas:
                hija = tasks_service.crear(
                    session,
                    proyecto.id,
                    TareaIn(titulo=titulo_hija, duracion=duracion, parent_id=padre.id),
                )
                por_titulo[titulo_hija] = hija

        for predecesora, sucesora, lag in VINCULOS:
            dependencies_service.crear(
                session,
                proyecto.id,
                DependenciaIn(
                    predecessor_id=por_titulo[predecesora].id,
                    successor_id=por_titulo[sucesora].id,
                    lag=lag,
                ),
            )

        print(f"Proyecto de ejemplo creado: http://127.0.0.1:8000/proyectos/{proyecto.id}")


if __name__ == "__main__":
    main()
