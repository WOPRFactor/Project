"""El puerto del arranque propio: default fijo y validación con mensaje claro."""

import pytest

from app.config import PUERTO_POR_DEFECTO, puerto


def test_sin_variable_usa_el_default(monkeypatch):
    monkeypatch.delenv("WOPR_PORT", raising=False)
    assert puerto() == PUERTO_POR_DEFECTO == 1983


def test_un_puerto_valido_se_respeta(monkeypatch):
    monkeypatch.setenv("WOPR_PORT", "8080")
    assert puerto() == 8080


@pytest.mark.parametrize("crudo", ["abc", "-1", "0", "70000", "80.5"])
def test_un_puerto_roto_frena_con_mensaje_claro(monkeypatch, crudo):
    monkeypatch.setenv("WOPR_PORT", crudo)
    with pytest.raises(SystemExit) as error:
        puerto()
    assert "WOPR_PORT" in str(error.value)
