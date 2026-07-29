"""Los controles del registro de riesgos. Módulo puro: sin base, sin sesión.

Cada test de acá es una forma concreta en que un registro de riesgos se muere: se
carga y no se define qué hacer, se define un plan que no se escribe, se promete una
baja que no se estima, o se pone una fecha de revisión y nadie vuelve.
"""

from datetime import date

from app.models import EstadoRiesgo, Respuesta, Riesgo
from app.services import riesgos_alertas as alertas_service

HOY = date(2026, 7, 29)


def riesgo(**campos) -> Riesgo:
    base = dict(id=1, project_id=1, descripcion="Se cae el ambiente",
                probabilidad=4, impacto=4)
    return Riesgo(**(base | campos))


def claves(riesgos, hoy=HOY) -> set[str]:
    return {a.clave for a in alertas_service.revisar(riesgos, hoy)}


def test_un_riesgo_sin_respuesta_se_avisa():
    assert "sin_respuesta" in claves([riesgo()])


def test_una_respuesta_activa_sin_plan_escrito_se_avisa():
    """Decidir «mitigar» sin escribir qué se hace es no haber decidido nada."""
    assert "sin_plan_escrito" in claves([riesgo(respuesta=Respuesta.mitigar)])


def test_aceptar_no_pide_plan_escrito():
    """Aceptar es no hacer nada a propósito: no hay plan que escribir."""
    sin_plan = claves([riesgo(respuesta=Respuesta.aceptar)])
    assert "sin_plan_escrito" not in sin_plan
    assert "sin_residual" not in sin_plan


def test_un_plan_sin_residual_estimado_se_avisa():
    """Sin residual no hay con qué comparar: el plan no se puede evaluar."""
    con_plan = riesgo(respuesta=Respuesta.mitigar, mitigacion="Doble proveedor")
    assert "sin_residual" in claves([con_plan])


def test_el_residual_no_declarado_no_supone_ninguna_baja():
    """Que nadie lo haya estimado no puede leerse como «el riesgo bajó»."""
    r = riesgo(respuesta=Respuesta.mitigar, mitigacion="Doble proveedor")
    assert r.severidad_residual == r.severidad == 16


def test_un_residual_peor_que_el_inherente_es_un_error_de_carga():
    peor = riesgo(probabilidad_residual=5, impacto_residual=5)
    alertas = alertas_service.revisar([peor], HOY)
    assert "residual_peor" in {a.clave for a in alertas}
    assert any(a.grave for a in alertas if a.clave == "residual_peor")


def test_un_plan_que_deja_todo_igual_se_avisa():
    igual = riesgo(respuesta=Respuesta.mitigar, mitigacion="Reunión semanal",
                   probabilidad_residual=4, impacto_residual=4)
    assert "plan_sin_efecto" in claves([igual])


def test_un_plan_bien_cargado_no_deja_pendientes():
    completo = riesgo(
        respuesta=Respuesta.mitigar, mitigacion="Doble proveedor",
        probabilidad_residual=2, impacto_residual=3,
        disparador="El proveedor no confirma la fecha",
        revisar_el=date(2026, 8, 30),
    )
    assert alertas_service.al_dia([completo], HOY)


def test_la_revision_vencida_es_grave():
    vencido = riesgo(revisar_el=date(2026, 7, 1))
    alertas = {a.clave: a for a in alertas_service.revisar([vencido], HOY)}
    assert alertas["revision_vencida"].grave


def test_la_revision_de_hoy_todavia_no_esta_vencida():
    assert "revision_vencida" not in claves([riesgo(revisar_el=HOY)])


def test_un_riesgo_critico_sin_fecha_de_revision_se_avisa():
    assert "grave_sin_revision" in claves([riesgo(probabilidad=5, impacto=5)])


def test_un_riesgo_chico_sin_fecha_de_revision_no_molesta():
    """Poner fecha de revisión a los veinte riesgos leves es cómo se abandona un registro."""
    chico = riesgo(probabilidad=1, impacto=2, respuesta=Respuesta.aceptar)
    assert "grave_sin_revision" not in claves([chico])
    assert "sin_disparador" not in claves([chico])


def test_un_riesgo_materializado_es_grave():
    """Ya no es un riesgo: es un problema, y debería estar en el cronograma."""
    paso = riesgo(estado=EstadoRiesgo.materializado)
    alertas = {a.clave: a for a in alertas_service.revisar([paso], HOY)}
    assert alertas["materializado"].grave


def test_los_cerrados_no_generan_pendientes():
    cerrado = riesgo(estado=EstadoRiesgo.cerrado, revisar_el=date(2020, 1, 1))
    assert alertas_service.revisar([cerrado], HOY) == []


def test_cada_alerta_dice_qué_riesgos_la_tienen():
    uno = riesgo(id=7)
    otro = riesgo(id=9, respuesta=Respuesta.aceptar)
    alertas = {a.clave: a for a in alertas_service.revisar([uno, otro], HOY)}
    assert alertas["sin_respuesta"].riesgos == (7,)
    assert alertas["sin_respuesta"].cuantos == 1


def test_lo_grave_va_primero():
    lista = [riesgo(id=1), riesgo(id=2, estado=EstadoRiesgo.materializado)]
    alertas = alertas_service.revisar(lista, HOY)
    assert alertas[0].clave == "materializado"
