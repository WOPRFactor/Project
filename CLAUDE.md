# WOPR Proyectos

Planificador de proyectos personal de Ariel, estilo MS Project pero local y propio:
tareas con subtareas, dependencias Fin→Inicio, y un timeline semanal (Gantt) con fechas
**calculadas** por un motor de scheduling. App web **local** (un usuario, sin auth).
El plan de obra completo, con fases, reglas del motor y criterios de hecho, está en
`PLAN-DE-OBRA.md` — leelo antes de implementar cualquier fase.

## Stack

Python 3.12 · FastAPI · SQLModel sobre SQLite · Jinja2 + HTMX (vendoreado en `static/`,
sin CDN) · timeline pintado server-side con CSS Grid · openpyxl para importar planillas ·
entorno y dependencias con `uv`.

## Comandos

```bash
uv sync                                # instalar dependencias
uv run uvicorn app.main:app --reload   # levantar en http://127.0.0.1:8000
uv run pytest                          # correr tests
```

## Arquitectura

Dirección de dependencias única: `routers → services → engine | models/db`.

- `app/engine/` — **el corazón**: motor de scheduling en Python puro. No importa FastAPI
  ni SQLModel; entra y sale por las dataclasses de `engine/types.py`. Se testea sin DB y
  sin server, y es el módulo con mayor densidad de tests del repo.
- `app/routers/` — HTTP puro: parsear request, llamar al service, renderizar. Sin lógica.
- `app/services/` — lógica de negocio; `services/schedule.py` puentea models → engine.
  No importan FastAPI ni templates.
- `app/models.py` — `Project`, `Task` (árbol vía `parent_id`), `Dependency`, enums.
- `app/migraciones.py` — agrega al arranque las columnas nuevas a una base ya
  existente. Campo nuevo en un modelo = anda solo; renombrar o borrar necesita más.
- `app/templates/` — Jinja2 con parciales para HTMX; el Gantt es HTML/CSS generado, y
  las flechas entre barras un SVG superpuesto cuya geometría calcula `engine/timeline.py`
  (es geometría pura, se testea sin navegador).

## Reglas del motor (v1 — no ampliar sin tocar el plan)

- Tarea con hijas = *resumen*: sin duración propia, fechas por rollup (envolvente).
- Duración 0 = **hito**: inicio y fin el mismo día, y no consume tiempo — lo que
  depende de un hito arranca el mismo día que el hito (`scheduler.salto_tras`).
- Dependencias **FS / SS / FF con lag** (días hábiles, negativo = adelanta), solo entre
  tareas hoja. SS existe porque el trabajo que corre *en paralelo* a otro (supervisar
  mientras se ejecuta) declarado como FS empuja el cronograma. Ciclos: detectados y
  rechazados al guardar, con error claro — jamás un 500 ni un loop.
- **El import no confía en las fechas de la planilla, pero tampoco las tira.** Las usa
  para detectar dependencias mal declaradas (`services/importar_diagnostico.py`): compara
  *relaciones*, no fechas absolutas, así un corrimiento global no genera ruido.
- Duración en **días hábiles** (L-V, sin feriados en v1). Restricción opcional por
  tarea: "no arrancar antes de X" (SNET).
- **Ámbito** por tarea (proyecto / seguimiento / control): afecta el *reporte*, nunca
  el cálculo. Separa el alcance comprometido del acompañamiento posterior.
- **Peso** por tarea: se declara como **% del padre**, nunca del proyecto. Así cada
  nivel cierra por su cuenta y agregar una tarea no rompe la suma del árbol entero.
  El peso absoluto es derivado (se multiplica desde la raíz) y no se guarda. `None` =
  "repartir en partes iguales lo que sobre". Que un nivel no dé 100 **se avisa, no se
  bloquea**: frenar la carga a mitad de camino sería infumable. El avance del proyecto
  es **ponderado** — Σ (peso absoluto × avance de la tarea) —, porque contar cabezas
  hace pesar lo mismo una firma de acta de un día que 120 días de acompañamiento.
- **Responsable = persona del proyecto**, no texto por tarea. La celda sigue siendo
  texto libre con autocompletado y el service la resuelve contra los contactos
  existentes, uniendo por nombre normalizado (sin acentos ni mayúsculas). Obligar a
  dar de alta a alguien antes de escribirlo se abandona a la tercera fila.
- **Estados definibles por proyecto.** El nombre y el color los elige el usuario; lo
  único que el motor necesita saber de un estado es `es_final`. Nunca comparar contra
  el string "hecha". `avance_sugerido` es lo que la tarea aporta al avance ponderado
  mientras no exista avance real por tarea.
- **Duración optimista / probable / pesimista**: el motor calcula los tres escenarios
  (`Escenario`) y la app muestra la ventana de fin. Sin rango declarado, los tres
  coinciden.
- Recálculo total del cronograma en cada cambio — no optimizar lo que no duele.

## Convenciones

- **Tamaño:** objetivo ≤ 200 líneas por archivo, techo 300. Función ≤ ~40-50 líneas.
  Excepción justificada se documenta en una línea al tope. Se modulariza por
  *responsabilidad*, no por conteo.
- Un archivo, una responsabilidad. Capacidad nueva = archivo nuevo que respeta el
  contrato, no crecimiento del existente.
- Todo cambio de lógica llega con su test; los del engine no tocan la DB; los de
  services no levantan el server.
- **Un control nuevo se prueba tocándolo.** `tests/navegador/` abre Chromium y hace
  clic; se saltea solo si no hay navegador. Existe porque dos bugs seguidos —el
  selector de columnas y la barra de vista entera— pasaron toda la suite: la lógica
  estaba bien y lo que no andaba era el control, "verificado" pasando parámetros por
  URL, que ejercita el servidor y saltea la interfaz.
- UI en castellano.

## Seguridad

- La app bindea **solo `127.0.0.1`**. Si alguna vez se expone fuera de localhost,
  auth + HTTPS son requisito previo, no deuda técnica.
- Todo input externo se valida con Pydantic en el borde: tipos, longitudes, enums
  cerrados, duración entera > 0, fechas parseadas estricto.
- El grafo de dependencias también es input: se valida (ciclos, referencias colgantes,
  dependencias a resúmenes) antes de calcular.
- Acceso a datos solo por ORM (SQLModel). SQL concatenado a mano: nunca.
- Jinja2 con autoescape activo; prohibido `|safe` sobre contenido de usuario.
- Sin secretos en el repo ni en el código; si aparece uno, va por variable de entorno.
- Debug apagado por default; los errores al navegador no muestran stack traces.
- La DB SQLite (`*.db`) no se commitea.

## Riesgos

El registro vive en `models_riesgo.py` y no toca el cronograma: ningún riesgo mueve
una fecha. Lo que lo mantiene vivo son cuatro distinciones, y ninguna es cosmética.

- **Inherente y residual son dos números distintos.** Probabilidad e impacto son el
  riesgo como está hoy; el residual es el mismo par *después* de ejecutar la
  respuesta, se declara aparte y **no se deriva** — cuánto baja un plan lo estima una
  persona. `None` = todavía no se estimó, y eso **nunca** se lee como una baja: la
  lectura cae al inherente. Se dibujan los dos cuadrantes: mostrar solo el residual
  esconde de qué tamaño era el problema, mostrar solo el inherente hace parecer que
  no se hizo nada.
- **La respuesta es una decisión, no un texto.** Evitar / mitigar / transferir /
  aceptar / escalar, y `sin_definir` como default a propósito: poder contar los que
  nadie decidió todavía es lo que hace útil el registro.
- **El plan vive en el cronograma.** `mitigacion_task_id` apunta a la tarea que
  ejecuta la respuesta; un plan que no está en el cronograma no tiene fecha, ni
  responsable, ni lugar donde verse.
- **`riesgos_alertas.py` avisa, nunca bloquea.** Un riesgo a medio cargar es un
  estado legítimo; frenar la carga es la forma más rápida de que nadie cargue
  riesgos. Los cerrados quedan afuera de todo.

Responsable = persona del proyecto, igual que en la grilla y por la misma razón.

## La grilla (Fase 7)

La grilla **es** la aplicación, como en MS Project o Smartsheet: cada celda se edita
en el lugar y cada cambio recalcula el cronograma entero. No hay formularios aparte.

- Columnas editables: WBS, Tarea, Resp., Predec., Días, Opt·Pes, Inicio, **Crít.**,
  **Peso**, **Avance**, **Riesgo**, **Estado**, Ámbito. Calculadas (nunca editables): Fin y el % del proyecto
  que se muestra al lado del peso, y el **Desvío** contra la línea base vigente.
- **Criticidad ≠ ruta crítica.** `Task.critica` es criticidad *de negocio*: la marca
  el usuario por KPI o impacto, y es la que pinta la barra en rojo. La ruta crítica
  del motor (holgura cero) es otra cosa y se expone como `Fila.sin_holgura` y como
  la holgura en días. Nunca se pisan entre sí.
- Arriba de la grilla, el **resumen** muestra inicio, fin, próximo hito y avance; abajo,
  un bloque por ámbito con su **ventana** (calendario, se superponen entre sí) y su
  **esfuerzo** (suma de duraciones, es trabajo). Dos unidades distintas, nunca juntas.
  La holgura se mide contra el fin del **ámbito** de cada tarea, no contra el fin
  global: si no, el acompañamiento posterior le regala meses de margen al resto. Vive dentro del tablero para recalcularse en
  cada cambio. La **fecha de inicio del proyecto se edita ahí mismo**: moverla
  recalcula todas las fechas conservando duraciones y dependencias.
- **Inicio** solo es editable si la tarea no tiene predecesoras; si las tiene, la fecha
  la manda la dependencia y se muestra en gris.
- Las **predecesoras se escriben por código WBS**: `1.3`, `1.3+2` (espera 2 días
  hábiles), `1.3-1` (solapa 1). Varias, separadas por coma. La celda es la fuente de
  verdad: lo que no está escrito, se borra.
- El **código WBS** se genera al crear la fila y después queda estable — renumerar es
  una acción explícita, porque reescribirlo rompería las referencias escritas a mano.
  Es único en todo el proyecto, no solo entre hermanas.
