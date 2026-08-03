"""Autorización (Fase 11): un test por verbo mutante, no una inspección visual.

Las dos reglas que se verifican acá, ruta por ruta:

- **Al ajeno, 404** — no 403: un 403 confirmaría que el proyecto existe.
- **Al lector, 403** — sabe que existe y no puede escribir, aunque arme el POST
  a mano. Esconder el botón en la UI no es un control.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import csrf as csrf_service
from app.auth import sesion as sesion_service
from app.db import get_session
from app.main import app
from app.models_auth import Rol
from app.schemas import ProyectoIn, TareaIn
from app.services import arbol as arbol_service
from app.services import miembros as miembros_service
from app.services import projects as projects_service
from app.services import usuarios as usuarios_service
from app.services.miembros import MiembroInvalido

CLAVE = "clave-de-prueba-1983"
CUENTAS = {
    "duenio": "duenio@wopr.local",
    "editor": "editor@wopr.local",
    "lector": "lector@wopr.local",
    "ajeno": "ajeno@wopr.local",
}


@pytest.fixture(name="mundo")
def mundo_fixture():
    """Un proyecto con dueño, editor y lector — más un ajeno que no es miembro."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def sesion_de_prueba():
        with Session(engine) as session:
            yield session

    from datetime import date

    with Session(engine) as session:
        cuentas = {
            papel: usuarios_service.crear(session, mail, CLAVE, debe_cambiar=False)
            for papel, mail in CUENTAS.items()
        }
        proyecto = projects_service.crear(
            session, ProyectoIn(nombre="Con permisos", fecha_inicio=date(2026, 1, 5))
        )
        for papel, rol in [
            ("duenio", Rol.duenio), ("editor", Rol.editor), ("lector", Rol.lector)
        ]:
            miembros_service.agregar(
                session, proyecto.id, cuentas[papel].id, rol
            )
        tarea = arbol_service.agregar_al_final(
            session, proyecto.id, TareaIn(titulo="Una tarea", duracion=3)
        )
        datos = {
            "project_id": proyecto.id,
            "task_id": tarea.id,
            "ids": {papel: c.id for papel, c in cuentas.items()},
        }

    app.dependency_overrides[get_session] = sesion_de_prueba
    with TestClient(app, follow_redirects=False) as cliente:
        datos["cliente"] = cliente
        datos["engine"] = engine
        yield datos
    app.dependency_overrides.clear()


def entrar(mundo, papel: str):
    """Deja el cliente autenticado como ese papel, con su token CSRF puesto."""
    cliente = mundo["cliente"]
    cliente.cookies.clear()
    cliente.post("/ingresar", data={"mail": CUENTAS[papel], "password": CLAVE})
    token = cliente.cookies.get(sesion_service.COOKIE, "")
    cliente.headers.update({csrf_service.CABECERA: csrf_service.token_de(token)})
    return cliente


def rutas_mutantes(project_id: int, task_id: int) -> list[tuple[str, dict]]:
    """Un POST por cada cosa que escribe. Si se agrega una ruta, va acá."""
    p = f"/proyectos/{project_id}"
    return [
        (f"{p}/tareas/agregar", {}),
        (f"{p}/tareas/{task_id}/celda", {"titulo": "Cambiada"}),
        (f"{p}/tareas/{task_id}/insertar", {}),
        (f"{p}/tareas/{task_id}/indentar", {}),
        (f"{p}/tareas/{task_id}/desindentar", {}),
        (f"{p}/tareas/{task_id}/eliminar", {}),
        (f"{p}/tareas/{task_id}/riesgo", {"tildado": "1"}),
        (f"{p}/inicio", {"fecha_inicio": "2026-02-02"}),
        (f"{p}/renumerar", {}),
        (f"{p}/pesos/repartir", {"criterio": "duracion"}),
        (f"{p}/pegar", {"texto": "Colada"}),
        (f"{p}/estados", {"nombre": "Colado"}),
        (f"{p}/riesgos", {"descripcion": "Colado"}),
        (f"{p}/equipo", {"nombre": "Colado"}),
        (f"{p}/base/congelar", {"nombre": "Colada"}),
        (f"{p}/miembros", {"usuario_id": "1", "rol": "editor"}),
        (f"{p}/asistente/aplicar", {"carga": "[]"}),
        (f"{p}/editar", {"nombre": "X", "fecha_inicio": "2026-01-05"}),
        (f"{p}/eliminar", {}),
    ]


def rutas_de_lectura(project_id: int) -> list[str]:
    p = f"/proyectos/{project_id}"
    return [
        p, f"{p}/equipo", f"{p}/estados", f"{p}/riesgos", f"{p}/base",
        f"{p}/informe", f"{p}/miembros", f"{p}/export/json", f"{p}/export/markdown",
    ]


# --- el ajeno: para él el proyecto no existe ---

def test_el_ajeno_no_ve_el_proyecto_en_la_home(mundo):
    cliente = entrar(mundo, "ajeno")
    home = cliente.get("/")
    assert home.status_code == 200
    assert "Con permisos" not in home.text


def test_el_duenio_si_lo_ve_en_la_home(mundo):
    cliente = entrar(mundo, "duenio")
    assert "Con permisos" in cliente.get("/").text


@pytest.mark.parametrize("indice", range(9))
def test_el_ajeno_recibe_404_al_mirar(mundo, indice):
    cliente = entrar(mundo, "ajeno")
    ruta = rutas_de_lectura(mundo["project_id"])[indice]
    assert cliente.get(ruta).status_code == 404, ruta


@pytest.mark.parametrize("indice", range(19))
def test_el_ajeno_recibe_404_al_escribir(mundo, indice):
    """404 y no 403: un 403 le confirmaría que el proyecto existe."""
    cliente = entrar(mundo, "ajeno")
    ruta, datos = rutas_mutantes(mundo["project_id"], mundo["task_id"])[indice]
    respuesta = cliente.post(ruta, data=datos)
    assert respuesta.status_code == 404, f"{ruta} devolvió {respuesta.status_code}"


# --- el lector: ve todo, no escribe nada ---

@pytest.mark.parametrize("indice", range(9))
def test_el_lector_puede_mirar(mundo, indice):
    cliente = entrar(mundo, "lector")
    ruta = rutas_de_lectura(mundo["project_id"])[indice]
    assert cliente.get(ruta).status_code == 200, ruta


@pytest.mark.parametrize("indice", range(19))
def test_el_lector_no_escribe_aunque_arme_el_post(mundo, indice):
    cliente = entrar(mundo, "lector")
    ruta, datos = rutas_mutantes(mundo["project_id"], mundo["task_id"])[indice]
    respuesta = cliente.post(ruta, data=datos)
    assert respuesta.status_code == 403, f"{ruta} devolvió {respuesta.status_code}"


def test_la_grilla_del_lector_no_trae_controles_de_edicion(mundo):
    cliente = entrar(mundo, "lector")
    pagina = cliente.get(f"/proyectos/{mundo['project_id']}").text
    assert "Solo lectura" in pagina
    assert "+ Tarea" not in pagina
    assert "Importar planilla" not in pagina
    assert "readonly" in pagina  # las celdas no se editan


# --- el editor: escribe el cronograma, no toca lo del dueño ---

def test_el_editor_edita_la_grilla(mundo):
    cliente = entrar(mundo, "editor")
    p = mundo["project_id"]
    assert cliente.post(f"/proyectos/{p}/tareas/agregar").status_code == 200
    assert cliente.get(f"/proyectos/{p}").text.count('name="titulo"') == 2


@pytest.mark.parametrize("ruta,datos", [
    ("/estados", {"nombre": "Nuevo"}),
    ("/base/congelar", {"nombre": "Base"}),
    ("/miembros", {"usuario_id": "1", "rol": "editor"}),
    ("/editar", {"nombre": "X", "fecha_inicio": "2026-01-05"}),
    ("/eliminar", {}),
])
def test_el_editor_no_hace_lo_que_es_del_duenio(mundo, ruta, datos):
    cliente = entrar(mundo, "editor")
    respuesta = cliente.post(f"/proyectos/{mundo['project_id']}{ruta}", data=datos)
    assert respuesta.status_code == 403, f"{ruta} devolvió {respuesta.status_code}"


def test_el_duenio_administra_miembros(mundo):
    cliente = entrar(mundo, "duenio")
    p, ajeno = mundo["project_id"], mundo["ids"]["ajeno"]
    alta = cliente.post(f"/proyectos/{p}/miembros", data={"usuario_id": str(ajeno), "rol": "lector"})
    assert alta.status_code == 303

    # Ahora el ajeno entra… como lector.
    otro = entrar(mundo, "ajeno")
    assert otro.get(f"/proyectos/{p}").status_code == 200
    assert otro.post(f"/proyectos/{p}/tareas/agregar").status_code == 403


# --- invariantes del service ---

def test_un_proyecto_nunca_queda_sin_duenio(mundo):
    with Session(mundo["engine"]) as session:
        p, duenio = mundo["project_id"], mundo["ids"]["duenio"]
        with pytest.raises(MiembroInvalido):
            miembros_service.quitar(session, p, duenio)
        with pytest.raises(MiembroInvalido):
            miembros_service.cambiar_rol(session, p, duenio, Rol.lector)


def test_con_dos_duenios_si_se_puede_sacar_uno(mundo):
    with Session(mundo["engine"]) as session:
        p, editor, duenio = mundo["project_id"], mundo["ids"]["editor"], mundo["ids"]["duenio"]
        miembros_service.cambiar_rol(session, p, editor, Rol.duenio)
        miembros_service.quitar(session, p, duenio)
        assert miembros_service.rol_de(session, p, duenio) is None
        assert miembros_service.rol_de(session, p, editor) is Rol.duenio


def test_quien_crea_un_proyecto_es_su_duenio(mundo):
    cliente = entrar(mundo, "editor")
    creado = cliente.post(
        "/proyectos",
        data={"nombre": "Mío", "descripcion": "", "fecha_inicio": "2026-03-02"},
    )
    assert creado.status_code == 303
    nuevo_id = int(creado.headers["location"].rsplit("/", 1)[1])
    with Session(mundo["engine"]) as session:
        assert miembros_service.rol_de(session, nuevo_id, mundo["ids"]["editor"]) is Rol.duenio


def test_el_admin_de_la_instancia_entra_a_todo(mundo):
    with Session(mundo["engine"]) as session:
        usuarios_service.crear(
            session, "jefe@wopr.local", CLAVE, es_admin=True, debe_cambiar=False
        )
    cliente = mundo["cliente"]
    cliente.cookies.clear()
    cliente.post("/ingresar", data={"mail": "jefe@wopr.local", "password": CLAVE})
    assert cliente.get(f"/proyectos/{mundo['project_id']}").status_code == 200
