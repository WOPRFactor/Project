# WOPR Proyectos

Gestor de proyectos personal de Ariel. App web **local** (un usuario, sin auth):
proyectos con tareas, estados y prioridades, y un dashboard de "qué toca hoy".
El plan de obra completo, con fases y criterios de hecho, está en `PLAN-DE-OBRA.md` —
leelo antes de implementar cualquier fase.

## Stack

Python 3.12 · FastAPI · SQLModel sobre SQLite · Jinja2 + HTMX (vendoreado en `static/`,
sin CDN) · entorno y dependencias con `uv`.

## Comandos

```bash
uv sync                                # instalar dependencias
uv run uvicorn app.main:app --reload   # levantar en http://127.0.0.1:8000
uv run pytest                          # correr tests
```

## Arquitectura

Dirección de dependencias única: `routers → services → models/db`.

- `app/routers/` — HTTP puro: parsear request, llamar al service, renderizar. Sin lógica.
- `app/services/` — lógica de negocio pura. **No importan FastAPI ni templates**; se
  testean sin levantar la app.
- `app/models.py` — entidades SQLModel y enums de estado/prioridad.
- `app/templates/` — Jinja2 con parciales para HTMX.

## Convenciones

- **Tamaño:** objetivo ≤ 200 líneas por archivo, techo 300. Función ≤ ~40-50 líneas.
  Si un archivo se pasa con justificación (datos, generado), documentalo en una línea
  al tope. Se modulariza por *responsabilidad*, no por conteo.
- Un archivo, una responsabilidad. Capacidad nueva = archivo nuevo que respeta el
  contrato, no crecimiento del existente.
- Todo cambio de lógica llega con su test de service. Los tests no levantan el server.
- UI en castellano.

## Seguridad

- La app bindea **solo `127.0.0.1`**. Si alguna vez se expone fuera de localhost,
  auth + HTTPS son requisito previo, no deuda técnica.
- Todo input externo se valida con Pydantic en el borde: tipos, longitudes, enums
  cerrados para estado y prioridad.
- Acceso a datos solo por ORM (SQLModel). SQL concatenado a mano: nunca.
- Jinja2 con autoescape activo; prohibido `|safe` sobre contenido de usuario.
- Sin secretos en el repo ni en el código. Si aparece uno, va por variable de entorno.
- Debug apagado por default; los errores al navegador no muestran stack traces.
- La DB SQLite (`*.db`) no se commitea.
