"""La puerta (Fase 10): sesión obligatoria, CSRF en toda mutación, throttling.

Lo que se cuida acá no es que el login "ande", sino que **no se pueda pasar sin
él**: un anónimo con la URL exacta rebota, un POST sin token CSRF se rechaza, y
un intento de fuerza bruta se frena solo.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import csrf as csrf_service
from app.auth import hash as hash_service
from app.auth import sesion as sesion_service
from app.db import get_session
from app.main import app
from app.models_auth import Miembro, Rol, Usuario
from app.schemas import ProyectoIn
from app.services import projects as projects_service
from app.services import usuarios as usuarios_service
from app.services.usuarios import CredencialesInvalidas, CuentaInvalida

from .test_app import CLAVE, CUENTA, cliente_anonimo_fixture, cliente_fixture  # noqa: F401


@pytest.fixture(name="motor")
def motor_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="sesion_db")
def sesion_db_fixture(motor):
    with Session(motor) as session:
        yield session


# --- el hash nunca es reversible ni predecible ---

def test_el_hash_no_guarda_la_contrasena():
    hash_ = hash_service.hashear("clave-secreta-1983")
    assert "clave-secreta-1983" not in hash_
    assert hash_.startswith("$argon2id$")
    assert hash_service.verificar(hash_, "clave-secreta-1983")
    assert not hash_service.verificar(hash_, "otra-cosa")


def test_dos_hashes_de_la_misma_clave_son_distintos():
    """Con sal aleatoria: dos cuentas con la misma contraseña no se delatan."""
    de_ana = hash_service.hashear("misma-clave-1234")
    de_beto = hash_service.hashear("misma-clave-1234")
    assert de_ana != de_beto
    assert hash_service.verificar(de_ana, "misma-clave-1234")
    assert hash_service.verificar(de_beto, "misma-clave-1234")


def test_una_contrasena_corta_se_rechaza():
    assert hash_service.validar_fuerza("corta") is not None
    assert hash_service.validar_fuerza("suficientemente-larga") is None


# --- cuentas ---

def test_el_mail_se_normaliza(sesion_db: Session):
    usuarios_service.crear(sesion_db, "  Ariel@WOPR.Local ", "clave-de-prueba-123")
    assert usuarios_service.por_mail(sesion_db, "ariel@wopr.local") is not None
    with pytest.raises(CuentaInvalida):  # el mismo mail no entra dos veces
        usuarios_service.crear(sesion_db, "ariel@wopr.local", "otra-clave-1234")


def test_un_mail_sin_forma_valida_se_rechaza(sesion_db: Session):
    with pytest.raises(CuentaInvalida):
        usuarios_service.crear(sesion_db, "no-es-un-mail", "clave-de-prueba-123")


def test_no_se_puede_desactivar_al_ultimo_admin(sesion_db: Session):
    admin = usuarios_service.crear(
        sesion_db, "jefe@wopr.local", "clave-de-prueba-123", es_admin=True
    )
    with pytest.raises(CuentaInvalida):
        usuarios_service.cambiar_activo(sesion_db, admin.id, False)


def test_una_cuenta_desactivada_no_entra(sesion_db: Session):
    usuarios_service.crear(sesion_db, "jefe@wopr.local", "clave-de-prueba-123", es_admin=True)
    otro = usuarios_service.crear(sesion_db, "otro@wopr.local", "clave-de-prueba-123")
    usuarios_service.cambiar_activo(sesion_db, otro.id, False)
    with pytest.raises(CredencialesInvalidas):
        usuarios_service.autenticar(sesion_db, "otro@wopr.local", "clave-de-prueba-123")


def test_el_mensaje_de_credenciales_no_distingue_los_casos(sesion_db: Session):
    """Un mensaje distinto por cuenta inexistente le regalaría la lista al atacante."""
    usuarios_service.crear(sesion_db, "existe@wopr.local", "clave-de-prueba-123")

    with pytest.raises(CredencialesInvalidas) as sin_cuenta:
        usuarios_service.autenticar(sesion_db, "no-existe@wopr.local", "loquesea-1234")
    usuarios_service.olvidar_intentos()
    with pytest.raises(CredencialesInvalidas) as mal_clave:
        usuarios_service.autenticar(sesion_db, "existe@wopr.local", "incorrecta-1234")
    assert str(sin_cuenta.value) == str(mal_clave.value)


def test_el_throttling_frena_la_fuerza_bruta(sesion_db: Session):
    usuarios_service.crear(sesion_db, "victima@wopr.local", "clave-de-prueba-123")
    for _ in range(3):
        with pytest.raises(CredencialesInvalidas):
            usuarios_service.autenticar(sesion_db, "victima@wopr.local", "mala-1234")

    # Al cuarto intento ya hay espera acumulada: ni siquiera se prueba la clave.
    with pytest.raises(CredencialesInvalidas) as error:
        usuarios_service.autenticar(sesion_db, "victima@wopr.local", "clave-de-prueba-123")
    assert error.value.espera > 0


def test_cambiar_la_contrasena_cierra_las_sesiones(sesion_db: Session):
    usuario = usuarios_service.crear(sesion_db, "ariel@wopr.local", "clave-de-prueba-123")
    abierta = sesion_service.abrir(sesion_db, usuario)
    assert sesion_service.leer(sesion_db, abierta.token) is not None

    usuarios_service.cambiar_password(
        sesion_db, usuario, "clave-de-prueba-123", "clave-nueva-4567", "clave-nueva-4567"
    )
    assert sesion_service.leer(sesion_db, abierta.token) is None


def test_una_sesion_vencida_no_vale(sesion_db: Session):
    from datetime import datetime, timedelta

    usuario = usuarios_service.crear(sesion_db, "ariel@wopr.local", "clave-de-prueba-123")
    abierta = sesion_service.abrir(sesion_db, usuario)
    abierta.expira_el = datetime.now() - timedelta(seconds=1)
    sesion_db.add(abierta)
    sesion_db.commit()

    from app.models_auth import Sesion
    from sqlmodel import select

    assert sesion_service.leer(sesion_db, abierta.token) is None
    # Y además se limpió sola de la tabla: no hace falta una tarea programada.
    assert sesion_db.exec(select(Sesion)).first() is None


def test_un_token_inventado_no_abre_nada(sesion_db: Session):
    assert sesion_service.leer(sesion_db, "token-inventado") is None
    assert sesion_service.leer(sesion_db, "") is None


# --- la puerta, por HTTP ---

RUTAS_PRIVADAS = [
    "/", "/proyectos/1", "/proyectos/1/equipo", "/proyectos/1/estados",
    "/proyectos/1/riesgos", "/proyectos/1/base", "/proyectos/1/informe",
    "/importar", "/proyectos/nuevo", "/admin/usuarios",
    "/proyectos/1/export/json",
]


@pytest.mark.parametrize("ruta", RUTAS_PRIVADAS)
def test_un_anonimo_no_entra_a_ninguna_pantalla(cliente_anonimo, ruta):
    respuesta = cliente_anonimo.get(ruta)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/ingresar")


MUTACIONES = [
    ("/proyectos", {"nombre": "Colada", "descripcion": "", "fecha_inicio": "2026-01-05"}),
    ("/proyectos/1/tareas/agregar", {}),
    ("/proyectos/1/eliminar", {}),
    ("/admin/usuarios", {"mail": "colado@wopr.local"}),
]


@pytest.mark.parametrize("ruta,datos", MUTACIONES)
def test_un_anonimo_no_escribe_nada(cliente_anonimo, ruta, datos):
    respuesta = cliente_anonimo.post(ruta, data=datos)
    assert respuesta.status_code in (303, 401)
    if respuesta.status_code == 303:
        assert respuesta.headers["location"].startswith("/ingresar")


def test_un_post_sin_csrf_se_rechaza(cliente_anonimo):
    """La sesión sola no alcanza: sin token, el POST no pasa (defensa anti-CSRF).

    Es exactamente el escenario del ataque: el navegador de la víctima tiene la
    cookie y la manda sola, pero el sitio atacante no puede leer el token.
    """
    cliente_anonimo.post("/ingresar", data={"mail": CUENTA, "password": CLAVE})
    assert cliente_anonimo.cookies.get(sesion_service.COOKIE)  # sesión válida

    respuesta = cliente_anonimo.post(
        "/proyectos",
        data={"nombre": "Desde otro sitio", "descripcion": "", "fecha_inicio": "2026-01-05"},
    )
    assert respuesta.status_code == 403
    assert "recargá" in respuesta.text.lower()


def test_un_csrf_de_otra_sesion_no_sirve(cliente):
    respuesta = cliente.post(
        "/proyectos/1/tareas/agregar",
        headers={csrf_service.CABECERA: csrf_service.token_de("token-de-otra-sesion")},
    )
    assert respuesta.status_code == 403


def test_un_formulario_html_con_token_oculto_funciona(cliente_anonimo):
    """El campo oculto (formularios sin HTMX) vale igual que la cabecera, y el
    endpoint tiene que seguir viendo el resto del body: el middleware lo repone."""
    cliente_anonimo.post("/ingresar", data={"mail": CUENTA, "password": CLAVE})
    token = cliente_anonimo.cookies.get(sesion_service.COOKIE)

    alta = cliente_anonimo.post(
        "/admin/usuarios",
        data={
            "mail": "porformulario@wopr.local",
            "nombre": "Por formulario",
            csrf_service.CAMPO: csrf_service.token_de(token),
        },
    )
    assert alta.status_code == 303
    # El endpoint recibió el mail (el body sobrevivió a la lectura del middleware).
    assert "porformulario%40wopr.local" in alta.headers["location"]


def test_el_token_csrf_esta_atado_a_la_sesion():
    assert csrf_service.token_de("sesion-a") != csrf_service.token_de("sesion-b")
    assert csrf_service.token_de("") == ""
    assert not csrf_service.es_valido("sesion-a", "")
    assert csrf_service.es_valido("sesion-a", csrf_service.token_de("sesion-a"))


def test_el_login_y_la_salida_funcionan(cliente_anonimo):
    entrada = cliente_anonimo.post("/ingresar", data={"mail": CUENTA, "password": CLAVE})
    assert entrada.status_code == 303
    token = cliente_anonimo.cookies.get(sesion_service.COOKIE)
    assert token

    cabeceras = {csrf_service.CABECERA: csrf_service.token_de(token)}
    assert cliente_anonimo.get("/").status_code == 200

    salida = cliente_anonimo.post("/salir", headers=cabeceras)
    assert salida.status_code == 303
    # Sin sesión otra vez: la home vuelve a rebotar al login.
    assert cliente_anonimo.get("/").status_code == 303


def test_credenciales_malas_no_abren_sesion(cliente_anonimo):
    respuesta = cliente_anonimo.post(
        "/ingresar", data={"mail": CUENTA, "password": "no-es-la-clave"}
    )
    assert respuesta.status_code == 401
    assert not cliente_anonimo.cookies.get(sesion_service.COOKIE)


def test_la_cookie_de_sesion_es_httponly(cliente_anonimo):
    respuesta = cliente_anonimo.post("/ingresar", data={"mail": CUENTA, "password": CLAVE})
    cookie = respuesta.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_el_hash_nunca_sale_en_una_respuesta(cliente):
    """Ni en la pantalla de cuentas ni en ningún lado."""
    pantalla = cliente.get("/admin/usuarios")
    assert pantalla.status_code == 200
    assert "$argon2id$" not in pantalla.text


def test_un_usuario_comun_no_entra_a_las_cuentas():
    """El rol se verifica en el endpoint, no escondiendo el botón en la UI."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def sesion_de_prueba():
        with Session(engine) as session:
            yield session

    with Session(engine) as session:
        usuarios_service.crear(session, CUENTA, CLAVE, es_admin=True, debe_cambiar=False)
        usuarios_service.crear(
            session, "comun@wopr.local", CLAVE, es_admin=False, debe_cambiar=False
        )

    app.dependency_overrides[get_session] = sesion_de_prueba
    with TestClient(app, follow_redirects=False) as cliente:
        cliente.post("/ingresar", data={"mail": "comun@wopr.local", "password": CLAVE})
        assert cliente.get("/admin/usuarios").status_code == 403

        token = cliente.cookies.get(sesion_service.COOKIE)
        alta = cliente.post(
            "/admin/usuarios",
            data={"mail": "colado@wopr.local"},
            headers={csrf_service.CABECERA: csrf_service.token_de(token)},
        )
        assert alta.status_code == 403  # tampoco puede crear cuentas
    app.dependency_overrides.clear()


def test_el_primer_usuario_se_crea_cuando_no_hay_ninguno():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def sesion_de_prueba():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sesion_de_prueba
    with TestClient(app, follow_redirects=False) as cliente:
        # Sin cuentas, el login manda a crear la primera.
        assert cliente.get("/ingresar").headers["location"] == "/primer-usuario"
        creado = cliente.post(
            "/primer-usuario",
            data={"mail": "primero@wopr.local", "nombre": "Ariel",
                  "password": "clave-de-prueba-123"},
        )
        assert creado.status_code == 303
        assert cliente.cookies.get(sesion_service.COOKIE)
        # Con una cuenta ya creada, la pantalla no se puede volver a usar.
        assert cliente.get("/primer-usuario").headers["location"] == "/ingresar"
    app.dependency_overrides.clear()


def test_el_primer_usuario_adopta_los_proyectos_que_ya_estaban():
    """Los proyectos de la etapa monousuario tienen que quedar con dueño.

    La adopción del arranque no alcanza: cuando la app arranca sobre una base sin
    cuentas todavía no hay a quién dárselos, y el proyecto quedaba sin fila de dueño.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        proyecto = projects_service.crear(
            session, ProyectoIn(nombre="De antes", fecha_inicio=date(2026, 1, 5))
        )
        proyecto_id = proyecto.id

    def sesion_de_prueba():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sesion_de_prueba
    with TestClient(app, follow_redirects=False) as cliente:
        cliente.post(
            "/primer-usuario",
            data={"mail": "primero@wopr.local", "nombre": "Ariel",
                  "password": "clave-de-prueba-123"},
        )
    app.dependency_overrides.clear()

    with Session(engine) as session:
        usuario = session.exec(select(Usuario)).one()
        miembro = session.exec(select(Miembro)).one()
        assert miembro.project_id == proyecto_id
        assert miembro.usuario_id == usuario.id
        assert miembro.rol == Rol.duenio
