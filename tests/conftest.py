from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.models import Project
from app.schemas import ProyectoIn
from app.services import projects as projects_service


@pytest.fixture(name="session")
def session_fixture():
    """SQLite en memoria: los tests de services no tocan la DB del usuario."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="proyecto")
def proyecto_fixture(session: Session) -> Project:
    return projects_service.crear(
        session,
        ProyectoIn(nombre="Proyecto de prueba", fecha_inicio=date(2026, 1, 5)),
    )
