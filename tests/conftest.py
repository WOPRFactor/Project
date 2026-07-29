from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
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


@pytest.fixture(name="cliente")
def cliente_fixture():
    """La app entera contra una DB temporal. Para los tests que van por HTTP."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def sesion_de_prueba():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sesion_de_prueba
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


@pytest.fixture(name="proyecto")
def proyecto_fixture(session: Session) -> Project:
    return projects_service.crear(
        session,
        ProyectoIn(nombre="Proyecto de prueba", fecha_inicio=date(2026, 1, 5)),
    )
