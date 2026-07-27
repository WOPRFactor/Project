# Plan de obra — WOPR Proyectos

Gestor/planificador de proyectos personal de Ariel. App web local: proyectos con fases,
tareas, estados y prioridades, más un dashboard de "qué toca hoy". Uso personal e
iterativo — se diseña simple y se hace crecer por fases.

## Resumen

| | |
|---|---|
| Qué es | App web local para crear y seguir proyectos (fases, tareas, estados, prioridades) |
| Para quién | Ariel, uso personal |
| Dónde corre | Local, navegador contra `127.0.0.1` — sin exposición de red |
| Datos | Propios (proyectos y tareas personales), sin secretos ni datos de terceros en v1 |
| Producción | No — herramienta personal iterativa |

## Supuestos

Lo que no preguntamos, lo asumimos. Corregí lo que no cierre antes de arrancar la Fase 1.

1. **Alcance v1:** proyectos → tareas (con estado, prioridad, fecha límite opcional y
   notas). Las "fases" de un proyecto se modelan como agrupador simple de tareas, no como
   entidad con workflow propio.
2. **Un solo usuario, sin login.** La app solo escucha en `127.0.0.1`; no hay auth en v1.
   Si algún día se expone fuera de la máquina, auth pasa a ser requisito previo (está en
   Riesgos).
3. **Persistencia en SQLite**, un archivo local versionable por backup, no por git.
4. **Sin integración con wopr-asistente en v1.** El export a Markdown/JSON (Fase 5) deja
   la puerta abierta para conectarlo después.
5. **Idioma de la UI: castellano.**

## Arquitectura y stack

> **Decisión a validar** — recomendación con alternativa; confirmá o cambiá antes de la Fase 1.

**Recomendado: Python 3.12 + FastAPI + Jinja2 + HTMX + SQLite (vía SQLModel).**
Python primero, como siempre, y para una web local liviana esta combinación es la de menor
complejidad real: un solo proceso, cero build step, cero npm. HTMX da interactividad de
sobra para un CRUD con dashboard sin arrastrar un frontend aparte. FastAPI aporta
validación Pydantic en los bordes (seguridad de entrada gratis) y SQLModel da ORM
parametrizado sobre SQLite (nada de SQL a mano).

**Alternativa razonable:** Flask + Jinja2 + SQLAlchemy. Menos conceptos que FastAPI si
querés lo mínimo absoluto; perdés la validación Pydantic automática y los docs de API.
Solo la elegiría si FastAPI te resulta ruido para algo tan chico.

**Descartado y por qué:** SPA (React/Svelte) + API — dos toolchains y un build step para
una app de un usuario; no se justifica. Servicio en cloud — suma deploy, auth y superficie
de ataque sin beneficio para uso personal local.

**Gestión de entorno:** `uv` (venv + lock de dependencias pinneadas).

### Superficie de ataque

- **Entra de afuera:** solo formularios/requests del navegador local. Todo input se valida
  con Pydantic en el borde (tipos, longitudes, enums de estado/prioridad).
- **Red:** la app *solo* bindea `127.0.0.1`. No hay puerto expuesto a la LAN.
- **Persistencia:** ORM parametrizado (SQLModel) — sin concatenación de SQL, nunca.
- **Salida:** Jinja2 con autoescape (default) — sin `|safe` sobre contenido de usuario.
- **Secretos:** v1 no tiene. Si aparece alguno (API key futura), va por variable de
  entorno, jamás hardcodeado ni commiteado.
- **Errores:** modo debug apagado por default; los errores al navegador no filtran stack
  traces (página de error genérica; el detalle va al log local).

## Estructura del repo

Modular desde el arranque: una responsabilidad por archivo, lógica separada del I/O,
objetivo ≤ 200 líneas por archivo (techo 300, excepción documentada en una línea).

```
wopr-proyectos/
├── CLAUDE.md
├── PLAN-DE-OBRA.md
├── README.md
├── pyproject.toml            # deps pinneadas, gestionado con uv
├── .gitignore
├── app/
│   ├── main.py               # crea la app, monta routers, arranque (solo wiring)
│   ├── config.py             # settings (host/puerto/ruta DB) desde env con defaults
│   ├── db.py                 # engine SQLite, sesión, init
│   ├── models.py             # Project, Task (SQLModel) + enums de estado/prioridad
│   ├── routers/
│   │   ├── projects.py       # rutas de proyectos (HTTP puro, delega en services)
│   │   ├── tasks.py          # rutas de tareas
│   │   └── dashboard.py      # home / vista "hoy"
│   ├── services/
│   │   ├── projects.py       # lógica de negocio de proyectos (pura, testeable aislada)
│   │   └── tasks.py          # lógica de tareas y priorización
│   └── templates/            # Jinja2 + parciales HTMX
├── static/                   # un CSS chico, htmx.min.js vendoreado
└── tests/
    ├── test_projects.py
    └── test_tasks.py
```

Dirección de dependencias única: `routers → services → models/db`. Los services no
importan nada de FastAPI ni de templates — se testean sin levantar la app.

## Fases

Cada fase termina con su *criterio de hecho* cumplido; ninguna se cierra si un archivo
supera el techo de 300 líneas o si el control de seguridad de la fase quedó afuera.

### Fase 1 — Esqueleto que arranca
Repo con `uv`, FastAPI montado, SQLite con modelos `Project` y `Task`, config por env,
página home vacía y healthcheck. Estructura modular completa aunque haya archivos casi
vacíos.
**Hecho cuando:** `uv run uvicorn app.main:app` levanta en `127.0.0.1:8000`, la home
responde, la DB se crea sola al primer arranque, bind verificado solo-localhost, y los
tests (aunque sean 2) corren verdes.

### Fase 2 — CRUD de proyectos
Crear, listar, editar y archivar proyectos (nombre, descripción, estado
activo/pausado/archivado, prioridad). Vistas server-rendered con parciales HTMX para
crear/editar sin recargar.
**Hecho cuando:** el ciclo completo se hace desde el navegador, todo input pasa por
validación Pydantic (nombre no vacío, enums cerrados), tests de service verdes, ningún
archivo pasado de límite.

### Fase 3 — Tareas dentro de proyectos
CRUD de tareas (título, notas, estado pendiente/en-curso/hecha, prioridad, fecha límite
opcional, agrupador de fase como texto libre). Vista detalle de proyecto con sus tareas,
toggle de estado inline vía HTMX.
**Hecho cuando:** una tarea vive su ciclo completo desde la vista de proyecto, el service
de tareas se testea aislado, y el borrado pide confirmación (acción destructiva).

### Fase 4 — Dashboard "qué toca hoy"
Home real: proyectos activos ordenados por prioridad, tareas vencidas y de hoy arriba,
filtros por estado/prioridad, búsqueda simple por texto.
**Hecho cuando:** la home muestra el día de un vistazo con datos reales, los filtros
combinan, y la búsqueda usa el ORM (sin SQL crudo).

### Fase 5 — Cierre v1: export, seeds y pasada de seguridad
Export/backup a JSON y a Markdown (un `.md` por proyecto, legible), script de seed con
datos de ejemplo, README con cómo correr y backupear. Pasada final de seguridad sobre
todo el repo.
**Hecho cuando:** el export produce archivos válidos, el README alcanza para levantar la
app en una máquina limpia, y la pasada final da limpia: input validado en bordes, cero
secretos en repo, deps pinneadas sin CVEs conocidos, errores sin stack trace al navegador,
bind solo-localhost re-verificado. Correr `/security-review` sobre el diff antes de cerrar.

## Prompts para Code

Uno por fase, en orden. Pegalos tal cual; cada uno asume el anterior terminado.

### Prompt Fase 1
> Leé CLAUDE.md y PLAN-DE-OBRA.md. Implementá la Fase 1 de WOPR Proyectos: proyecto
> Python 3.12 gestionado con uv; FastAPI + SQLModel + Jinja2; estructura de carpetas
> exacta del plan (app/routers, app/services, app/templates, static, tests). Modelos
> `Project` y `Task` con los enums de estado y prioridad del plan. Config en
> `app/config.py` leyendo env con defaults (host 127.0.0.1, puerto 8000, ruta de DB).
> La DB SQLite se inicializa sola al arrancar. Home vacía renderizada con Jinja y un
> healthcheck. Vendoreá htmx.min.js en static (sin CDN).
> Criterios de aceptación: la app levanta con `uv run uvicorn app.main:app` y SOLO
> bindea 127.0.0.1; dependencias pinneadas en pyproject; autoescape de Jinja activo;
> debug apagado por default; dos tests mínimos (healthcheck y creación de un Project
> vía service) verdes con pytest; ningún archivo > 300 líneas.

### Prompt Fase 2
> Implementá la Fase 2: CRUD completo de proyectos (crear, listar, editar, archivar) con
> vistas Jinja + parciales HTMX. Rutas en `app/routers/projects.py` (solo HTTP), lógica
> en `app/services/projects.py` (pura, sin imports de FastAPI). Validación Pydantic en
> el borde: nombre requerido con longitud máxima, estado y prioridad solo por enum.
> Criterios de aceptación: ciclo CRUD completo desde el navegador; input inválido
> devuelve error claro sin stack trace; tests del service cubriendo crear/editar/archivar
> y un caso de input inválido; ningún archivo > 300 líneas (objetivo 200).

### Prompt Fase 3
> Implementá la Fase 3: tareas dentro de proyectos según el plan (título, notas, estado,
> prioridad, fecha límite opcional, campo fase como texto). Vista detalle de proyecto con
> sus tareas agrupadas, toggle de estado inline con HTMX, borrado con confirmación.
> Misma separación: router delgado, service puro y testeado aislado.
> Criterios de aceptación: ciclo completo de una tarea desde la vista de proyecto; toda
> entrada validada en el borde; el borrado exige confirmación; tests de service verdes;
> límites de tamaño respetados.

### Prompt Fase 4
> Implementá la Fase 4: dashboard en la home según el plan — proyectos activos por
> prioridad, tareas vencidas y de hoy destacadas, filtros por estado/prioridad
> combinables, búsqueda por texto en títulos y notas. La lógica de ordenamiento y
> filtrado va en services y se testea con datos armados; las consultas usan el ORM,
> nada de SQL crudo.
> Criterios de aceptación: la home refleja el estado real de un vistazo; filtros y
> búsqueda combinan; tests de la lógica de priorización verdes; límites de tamaño
> respetados.

### Prompt Fase 5
> Implementá la Fase 5 y cerrá la v1: export a JSON (dump completo) y a Markdown (un .md
> por proyecto con sus tareas), script de seed con datos de ejemplo, README con
> instalación, uso y backup. Después hacé la pasada final de seguridad del plan: input
> validado en todos los bordes, cero secretos ni credenciales en el repo, dependencias
> pinneadas y sin CVEs conocidos, errores sin stack trace al navegador, bind
> solo-localhost verificado, autoescape activo sin `|safe` sobre datos de usuario.
> Corré `/security-review` sobre el diff y resolvé lo que salga antes de dar por cerrada
> la fase.
> Criterios de aceptación: export válido y legible; app levantable en máquina limpia
> siguiendo solo el README; pasada de seguridad limpia y review corrido.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| **Seguridad:** hoy el riesgo es bajo — sin red expuesta, sin secretos, un usuario. El riesgo real es el *scope creep*: exponerla en LAN o cloud "un rato" sin auth. | Regla dura: si algún día se expone fuera de `127.0.0.1`, auth + HTTPS son requisito previo, no deuda. Queda declarado acá y en CLAUDE.md. |
| Solapamiento con wopr-asistente: dos lugares para las mismas tareas. | v1 es standalone a propósito; el export (Fase 5) es el puente si después conviene unificar. Decisión consciente, no accidente. |
| Pérdida de datos (SQLite es un archivo local). | Export/backup de Fase 5 + recordatorio en README. La DB no va a git (.gitignore). |
| La app engorda a God-project (todo termina siendo "una tarea"). | Alcance v1 cerrado en Supuestos; features nuevas = fase nueva en este plan, no parches sueltos. |
