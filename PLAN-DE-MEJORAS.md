# Plan de mejoras — WOPR Proyectos v2

Continúa `PLAN-DE-OBRA.md`, que cubre las fases 1 a 9 (v1: motor de scheduling, grilla
editable, Gantt con flechas, ámbitos, import de planilla). Este documento cubre el salto
de v2: **la app deja de ser de una sola persona y empieza a rendir cuentas hacia afuera.**

Son dos capacidades distintas y conviene no confundirlas:

- **Multiusuario** es un cambio de *postura*. Hoy la app confía en todo lo que le llega
  porque del otro lado hay una sola persona en su propia máquina. Con dos usuarios eso se
  termina: cada consulta pasa a necesitar un dueño, cada escritura un permiso, y el
  proceso deja de estar solo detrás de `127.0.0.1`. Es la parte que tiene una **puerta de
  seguridad dura**: no se expone nada fuera de localhost hasta que auth y HTTPS estén
  cerrados.
- **Informes** es un cambio de *contenido*. Un informe no es la grilla impresa: es la
  comparación entre lo que se prometió y lo que está pasando. Eso hoy no se puede armar
  porque falta el término de comparación — no hay **línea base** ni **avance real**. Sin
  eso el "informe" es una foto sin desvío, que es exactamente lo que nadie necesita.

## Resumen

| | |
|---|---|
| Qué suma | Usuarios con permisos, trabajo simultáneo, línea base, avance real, informe imprimible |
| Para quién | Ariel (dueño), su equipo (carga), clientes y dirección (lectura del informe) |
| Dónde corre | Servidor propio o VPS. **El proceso sigue bindeando `127.0.0.1`**; el TLS lo termina un proxy adelante |
| Datos | Deja de ser solo de Ariel: hay datos de terceros y credenciales. Cambia la clasificación del proyecto |
| Producción | **Sí.** A partir de la Fase 13 esto es un servicio, no un experimento |

Ese último renglón es el que manda. Todo lo que en v1 se justificaba con "es local y lo uso
yo" deja de tener validez.

## Supuestos

Corregí lo que no cierre **antes de la Fase 10** — algunos cambian el modelo de datos.

1. **Los usuarios los da de alta el dueño. No hay auto-registro.** Es la simplificación más
   rentable de todo el plan: elimina de un saque el registro público, la verificación por
   mail, el "olvidé mi contraseña" con SMTP, y el abuso de altas. Ariel crea el usuario y
   entrega una contraseña de un solo uso que se cambia al primer login.
2. **Tres roles por proyecto: dueño / editor / lector.** El dueño administra miembros y
   línea base; el editor carga y edita tareas; el lector solo ve (grilla, Gantt e informe).
   Nada de permisos por tarea ni por columna: complejidad que no paga.
3. **Un `admin` global** (Ariel) que crea usuarios y ve todo. Uno, no un sistema de roles
   globales.
4. **Orden de magnitud: decenas de usuarios, no miles.** Define todas las decisiones de
   infraestructura de acá abajo. Si alguna vez son miles, se replantea; hoy dimensionar
   para eso sería pagar por adelantado algo que no va a pasar.
5. **Sin colaboración en vivo.** Dos personas pueden trabajar sobre el mismo proyecto, pero
   no ven el cursor del otro ni se sincronizan en tiempo real. Lo que sí se garantiza es
   que **nadie pisa el trabajo de otro en silencio** (Fase 12).
6. **El avance lo carga una persona.** No hay integración con Jira, ni con el repo, ni
   deducción automática de progreso.
7. **La línea base la congela el dueño explícitamente**, y puede haber varias (la aprobada,
   la re-planificada). Una sola está *vigente* y es contra la que se mide el desvío.
8. **El informe es un documento a fecha de corte**, no un dashboard vivo. Se genera, se
   mira, se imprime. Que la app tenga la grilla en vivo no lo reemplaza.
9. **Sin notificaciones por mail** en v2. Ni de alta de usuario, ni de tarea vencida. Sumar
   SMTP es sumar secretos, cola y modo de falla; si hace falta, es una fase propia.

## Arquitectura y stack

> **Decisiones a validar** — recomendación con alternativa. Confirmá antes de la Fase 10.

La forma de la app no cambia: FastAPI + Jinja + HTMX server-rendered, un proceso, cero
build step. Lo que cambia es lo que la rodea. Cinco decisiones:

**1. Identidad: sesión propia con tabla de sesiones, no cookie firmada.**
Recomendado: contraseñas con **argon2id** (`argon2-cffi`), y sesión como fila en la DB con
un token opaco en cookie `HttpOnly; Secure; SameSite=Lax`. Son unas 150 líneas.
*Por qué tabla y no cookie firmada:* una cookie firmada no se puede revocar antes de que
expire — si echás a alguien o se filtra una sesión, seguís esperando. Con tabla, "cerrar
sesión en todos lados" y "revocar a este usuario ya" son un `DELETE`.
*Alternativa:* `fastapi-users` (trae registro, reset, OAuth). Costo: una dependencia grande
que impone sus modelos, para resolver un registro público que decidimos no tener.

**2. HTTPS: lo termina un proxy adelante, nunca la app.**
Recomendado: **Caddy** delante (HTTPS automático con Let's Encrypt, renovación sola), la
app sigue escuchando en `127.0.0.1:8000`. Así la regla que ya está en CLAUDE.md se mantiene
literal: el proceso Python nunca escucha en una interfaz pública.
*Alternativa fuerte si el acceso es solo del equipo:* **Tailscale** (`tailscale serve`) —
certificado real en un nombre `*.ts.net`, **cero puertos abiertos a internet**, acceso desde
donde estén. Para una PYME donde los que cargan son tu gente, es más seguro que exponer un
443 público. Se puede combinar: Tailscale para el equipo, Caddy público solo si el cliente
necesita entrar a ver el informe.
*Descartado:* uvicorn con `--ssl-keyfile`. Mete TLS y renovación de certificados dentro del
proceso de la app, que es exactamente donde no querés que estén.

**3. Base: SQLite se queda, con WAL. Postgres es el upgrade documentado, no el default.**
Con decenas de usuarios y una carga dominada por lecturas, SQLite en modo WAL (lectores
concurrentes + un escritor, con `busy_timeout`) alcanza de sobra y evita un servicio más.
El límite honesto: **un escritor por vez**. Como cada edición recalcula el cronograma
entero, si alguna vez ves esperas al guardar, ese es el síntoma y ahí se migra.
*Alternativa:* Postgres desde el arranque. Costo: un servicio más, backups distintos.

**4. Migraciones: Alembic reemplaza a `migraciones.py`.**
`app/migraciones.py` resuelve "agregar columna a una base existente" y para v1 estuvo bien.
v2 suma seis tablas y una migración *de datos* (estado → % de avance), y encima ahora la
base tiene trabajo de otras personas adentro. Un script aditivo sin versiones ni vuelta
atrás es el lugar equivocado para descubrir un error.
*Alternativa:* seguir con `migraciones.py` y hacer cada cambio destructivo a mano con backup
previo. Es defendible mientras seas el único que toca el servidor; deja de serlo el día que
no lo seas.

**5. El informe se imprime desde el navegador. No hay motor de PDF en v2.**
Recomendado: una vista HTML con `@media print` (A4, saltos de página controlados, sin
navegación). Ctrl+P da un PDF idéntico al que daría una librería, con cero dependencias y
cero superficie nueva.
*Alternativa:* WeasyPrint, **solo si** aparece la necesidad de generar el PDF sin una
persona adelante (envío programado, adjuntarlo automáticamente). Ese día es una fase.

### Superficie de ataque

Esta sección es la que más cambia respecto de v1, y el motivo por el que el bloque de
multiusuario va antes que el de informes.

| Qué entra | Riesgo | Control |
|---|---|---|
| Login (usuario + contraseña) | Fuerza bruta, credential stuffing | argon2id, throttling progresivo por usuario+IP, sin distinguir "usuario inexistente" de "contraseña mala" |
| Cookie de sesión | Robo de sesión, fijación | Token opaco de 32 bytes de `secrets`, `HttpOnly; Secure; SameSite=Lax`, se **rota al iniciar sesión**, expira por inactividad y por antigüedad, revocable |
| Todo POST de la grilla | **CSRF** — hoy no hay ninguna defensa, y con cookies pasa a ser explotable | Token por sesión inyectado en `<meta>` y enviado por HTMX con `hx-headers`, validado en toda petición que no sea GET |
| `project_id` / `task_id` en la URL | **IDOR** — el riesgo más probable de todos: adivinar el id de otro proyecto | Ninguna consulta parte de un id crudo. Dependencia FastAPI `exige_lector/editor/dueño` que resuelve proyecto **y** permiso juntos, o 404 (404, no 403: no confirma que exista) |
| Planilla `.xlsx` subida | Bomba de descompresión, fórmulas, archivo gigante | Ya se lee con `read_only`/`data_only`; sumar **límite de tamaño** y de filas antes de parsear |
| Nombres, notas, responsables | XSS almacenado — ahora los escribe *otro* | Autoescape ya activo; la regla de nunca usar `\|safe` sobre datos de usuario pasa de higiene a control |
| Link de informe compartido (Fase 17, opcional) | Acceso sin cuenta | Token firmado con expiración, solo lectura, revocable, `X-Robots-Tag: noindex` |
| El proceso mismo | Exposición accidental | Sigue bindeando `127.0.0.1`. El proxy es lo único que escucha afuera |

**Secretos:** aparece el primero de la vida del proyecto (`SECRET_KEY` para firmar tokens).
Va por variable de entorno, se genera con `secrets.token_urlsafe(32)`, y **la app se niega a
arrancar en modo no-debug si no está o si es el default**. Nunca en el repo.

**CSP:** vendoreamos todo, así que `default-src 'self'` es alcanzable y vale la pena. Hay
dos deudas concretas que la bloquean hoy y hay que pagar en la Fase 13:
`app/templates/partials/tablero.html:78` y `:82` tienen `onclick=` inline, y
`app/templates/base.html:10` tiene un `<script>` inline. Van a un `.js` vendoreado o se
reemplazan por HTMX. Los `style=` del Gantt son geometría calculada y se quedan:
`style-src 'self' 'unsafe-inline'`.

## Estructura del repo

Se mantiene la dirección de dependencias única: `routers → services → engine | models/db`,
y el motor sigue sin importar FastAPI ni SQLModel. Lo nuevo:

```
app/
├── auth/                     # ★ identidad y permisos — cero lógica de negocio
│   ├── hash.py               # argon2id: hashear, verificar, detectar rehash
│   ├── sesion.py             # crear/leer/revocar sesión, cookie, rotación
│   ├── csrf.py               # emisión y validación del token
│   └── permisos.py           # dependencias: exige_lector / exige_editor / exige_dueño
├── models.py                 # + Usuario, Sesion, Miembro, Cambio
├── models_base.py            # LineaBase, LineaBaseTarea (aparte: otra responsabilidad)
├── engine/
│   └── comparar.py           # ★ desvío base vs actual — puro, se testea sin DB
├── services/
│   ├── usuarios.py           # alta, cambio de contraseña, bloqueo
│   ├── miembros.py           # quién puede qué en cada proyecto
│   ├── auditoria.py          # registrar y consultar cambios
│   ├── linea_base.py         # congelar, listar, marcar vigente
│   └── informe.py            # arma el DTO del informe; no renderiza
├── routers/
│   ├── auth.py               # login, logout, cambio de contraseña
│   ├── admin.py              # alta de usuarios (solo admin global)
│   ├── miembros.py
│   └── informe.py
├── templates/
│   ├── auth/                 # login, cambiar contraseña
│   └── informe/              # portada, cuerpo, CSS de impresión
└── migrations/               # Alembic
```

`app/migraciones.py` se elimina en la Fase 10, con su lógica trasladada a la primera
revisión de Alembic.

## Fases

Ninguna fase se cierra si un archivo supera 300 líneas, si su control de seguridad quedó
afuera, o si el módulo nuevo no se testea aislado.

El orden no es negociable en un punto: **el bloque A entero va antes de exponer nada.** Una
app a medio autenticar en internet es peor que una app sin autenticar en localhost.

### Bloque A — Multiusuario

#### Fase 10 — Identidad: usuarios, sesión y CSRF
Alembic reemplaza a `migraciones.py` (primera revisión = el esquema actual). Modelos
`Usuario` (mail único, hash argon2id, nombre, activo, `es_admin`, `debe_cambiar_password`)
y `Sesion` (token opaco, usuario, creada, último uso, expira). Login con throttling
progresivo y mensaje único ante credenciales inválidas. Cambio de contraseña obligatorio al
primer ingreso. Alta de usuarios solo para el admin global. Token CSRF por sesión, enviado
por HTMX vía `hx-headers` global, exigido en todo POST. **Todavía no se expone nada.**
**Hecho cuando:** un usuario nuevo entra, cambia su contraseña y navega; un POST sin token
CSRF válido da 403 sin stack trace; el token de sesión rota al iniciar sesión; diez intentos
fallidos frenan al atacante sin bloquear a la persona real de por vida; la app se niega a
arrancar sin `SECRET_KEY` en modo no-debug; el hash nunca aparece en un log ni en una
respuesta; `alembic upgrade head` reproduce la base desde cero **y** actualiza una base v1
existente sin perder datos.

#### Fase 11 — Autorización: proyectos con dueño y miembros
`Project` gana dueño. Tabla `Miembro` (proyecto, usuario, rol dueño/editor/lector). Las
dependencias `exige_lector / exige_editor / exige_dueño` resuelven proyecto y permiso en un
solo paso, y **ninguna ruta vuelve a partir de un id crudo**. El home lista solo los
proyectos donde sos miembro. El lector ve la grilla y el Gantt en modo lectura: sin celdas
editables, sin botones de mutación, y sin endpoint que lo acepte aunque arme el POST a mano.
Pantalla de miembros para el dueño.
**Hecho cuando:** existe un test por cada verbo que confirma que un usuario ajeno recibe
404 y que un lector recibe 403 al intentar escribir — la UI escondida no cuenta como
control; un proyecto sin miembros vivos no queda huérfano; borrar un usuario no borra los
proyectos donde era dueño.

#### Fase 12 — Trabajo simultáneo sin pisarse
SQLite en WAL con `busy_timeout`. `Task` gana `version`, que sube en cada escritura: la
celda manda la versión que leyó y, si no coincide, la respuesta es un 409 con la fila
recargada y un aviso claro de que otro la cambió — **nunca un guardado silencioso encima**.
Tabla `Cambio` (quién, cuándo, qué tarea, qué campo, de → a) alimentada por el service, no
por el router. Vista de historial por proyecto.
**Hecho cuando:** un test simula dos ediciones concurrentes sobre la misma tarea y la
segunda es rechazada con 409, no aplicada; el historial reconstruye qué pasó con una tarea;
el registro de auditoría no se puede editar desde la app.

#### Fase 13 — Exposición segura (la puerta)
La única fase que toca infraestructura. Proxy adelante (Caddy o Tailscale, según lo que se
valide arriba) con la app todavía en `127.0.0.1`. Headers: HSTS, `X-Content-Type-Options`,
`Referrer-Policy`, y CSP `default-src 'self'` — que exige pagar las tres deudas de inline JS
listadas en *Superficie de ataque*. Límite de tamaño y de filas en la subida de planillas.
Backup automático (`VACUUM INTO` con rotación) **con restauración probada**. `README-OPERACION.md`:
levantar, actualizar, rotar `SECRET_KEY`, restaurar un backup, dar de baja a alguien.
**Hecho cuando:** `curl` directo al puerto de la app desde otra máquina no responde; el sitio
saca A en un chequeo de TLS y headers; un backup se restaura **de verdad** en una máquina
limpia y la app levanta con esos datos; `/security-review` corrido sobre el diff completo del
bloque A y lo que salga, resuelto. Recién con esta fase cerrada se comparte la URL.

### Bloque B — Informes

#### Fase 14 — Línea base: el término de comparación
`LineaBase` (proyecto, nombre, fecha, quién, vigente) y `LineaBaseTarea` (inicio, fin,
duración, ámbito congelados). El dueño congela una línea base con un botón; puede haber
varias y una sola vigente. `engine/comparar.py` calcula el desvío en días hábiles por tarea
y por ámbito, con signo: adelanto negativo, atraso positivo. La grilla suma columna
**Desvío** y el Gantt puede mostrar la barra base en gris debajo de la actual.
**Hecho cuando:** el motor compara dos cronogramas sin tocar la DB, con tests para tarea
atrasada, adelantada, sin cambios, tarea nueva posterior a la base y tarea borrada; congelar
no altera ninguna fecha del cronograma vivo; un proyecto sin línea base sigue funcionando
igual y no muestra desvíos vacíos.

#### Fase 15 — Avance real
`Task` gana `avance` (0-100), `inicio_real` y `fin_real`. **El % pasa a ser la fuente de
verdad y `estado` se deriva** (0 = pendiente, 1-99 = en curso, 100 = hecha), para que no
puedan contradecirse; la migración de datos traduce los estados actuales. La grilla edita el
% en la celda. El resumen distingue **avance planificado a la fecha de corte** (cuánto
debería estar hecho) de **avance real** — que es la única forma de que "45%" signifique algo.
**Hecho cuando:** el avance planificado se calcula contra la línea base y tiene tests
propios; una tarea al 100% sin `fin_real` lo toma del cronograma; los estados de las tareas
existentes migran sin pérdida; el resumen y el Gantt siguen coherentes.

#### Fase 16 — El informe
Vista `/proyectos/{id}/informe?corte=YYYY-MM-DD`: portada (proyecto, cliente, fecha de
corte, autor), resumen ejecutivo (ventana por ámbito, avance real vs planificado, desvío
contra la base, próximo hito), tareas **atrasadas** y **en riesgo** (sin holgura y con
desvío), hitos con fecha base y fecha proyectada, qué se movió desde el último informe
(usando la auditoría de la Fase 12), y el Gantt. CSS `@media print` A4 con saltos
controlados. Export a Excel con openpyxl: grilla completa con fechas base, actuales y
desvío. Un lector puede generarlo; nadie que no sea miembro, no.
**Hecho cuando:** el informe se imprime a PDF desde el navegador y entra en A4 sin cortar
barras ni tablas; los números del informe coinciden con los de la grilla (test que compara
ambas salidas sobre el mismo proyecto); el Excel abre en Excel real sin advertencias;
`services/informe.py` arma datos y no HTML.

#### Fase 17 (opcional) — Link de solo lectura para el cliente
Un link firmado, con vencimiento y revocable, que muestra el informe **sin cuenta**. Es
comodidad real y superficie nueva a la vez: se hace solo si lo pedís, y con criterio de
aceptación propio — token de alta entropía, expiración corta por default, revocación desde
la app, `noindex`, sin exponer más que ese informe, y cada acceso registrado.

## Lo que este plan deja explícitamente afuera

El cerco contra el scope creep, que en un salto a multiusuario es donde más duele: sin
auto-registro ni OAuth; sin recuperación de contraseña por mail; sin permisos por tarea o
por columna; sin colaboración en tiempo real (websockets, cursores, CRDT); sin
notificaciones; sin recursos ni nivelación de carga; sin app móvil; sin API pública. Cada
uno es una fase propia contra este plan, no un agregado dentro de otra.

## Prompts para Code

Uno por fase, en orden; cada uno asume el anterior cerrado.

### Prompt Fase 10
> Leé CLAUDE.md, PLAN-DE-OBRA.md y PLAN-DE-MEJORAS.md. Implementá la Fase 10. Primero
> reemplazá `app/migraciones.py` por Alembic: la primera revisión reproduce el esquema
> actual, y `alembic upgrade head` tiene que actualizar una base v1 existente sin perder
> datos (probalo). Después el paquete `app/auth/`: `hash.py` (argon2id con argon2-cffi),
> `sesion.py` (tabla `Sesion` con token opaco de `secrets.token_urlsafe(32)`, cookie
> HttpOnly/Secure/SameSite=Lax, rotación al iniciar sesión, expiración por inactividad y
> por antigüedad, revocación) y `csrf.py` (token por sesión en `<meta>`, HTMX lo manda con
> `hx-headers` global, dependencia que lo exige en todo verbo que no sea GET). Modelo
> `Usuario` con mail único, hash, activo, es_admin y debe_cambiar_password. Router de login/
> logout/cambio de contraseña y router de admin para el alta. Throttling progresivo por
> usuario+IP y un único mensaje de error para credenciales inválidas.
> Criterios de aceptación: un POST sin CSRF válido da 403 sin stack trace; el token de
> sesión rota al login; la app se niega a arrancar en modo no-debug sin `SECRET_KEY` o con
> el valor default; el hash nunca sale en un log ni en una respuesta; tests de hash,
> sesión, CSRF y throttling; ningún archivo supera 300 líneas.

### Prompt Fase 11
> Implementá la Fase 11: autorización. `Project` gana dueño; tabla `Miembro` (proyecto,
> usuario, rol dueño/editor/lector). En `app/auth/permisos.py`, dependencias
> `exige_lector`, `exige_editor` y `exige_dueño` que resuelven proyecto y permiso en un solo
> paso y devuelven **404** (no 403) cuando el usuario no es miembro, para no confirmar que
> el proyecto existe. Recorré **todas** las rutas existentes de proyectos, tareas,
> dependencias, import y export: ninguna puede seguir partiendo de un id crudo. El home
> lista solo proyectos donde sos miembro. Modo lectura real para el lector: sin celdas
> editables y con el endpoint rechazando la escritura aunque arme el POST a mano. Pantalla
> de miembros para el dueño.
> Criterios de aceptación: un test por cada verbo mutante que confirme 404 para un usuario
> ajeno y 403 para un lector; test de que un proyecto no queda sin dueño; borrar un usuario
> no borra sus proyectos; límites de tamaño respetados.

### Prompt Fase 12
> Implementá la Fase 12: trabajo simultáneo. SQLite en WAL con `busy_timeout`. `Task` gana
> `version`, que se incrementa en cada escritura; las celdas de la grilla mandan la versión
> que leyeron y, si no coincide, la respuesta es 409 con la fila recargada y un aviso claro
> de que otra persona la cambió — nunca guardado silencioso encima. Tabla `Cambio` (quién,
> cuándo, tarea, campo, valor anterior, valor nuevo) escrita desde los services, no desde
> los routers. Vista de historial por proyecto, paginada.
> Criterios de aceptación: test que simula dos ediciones concurrentes sobre la misma tarea y
> verifica que la segunda es rechazada y no aplicada; el historial reconstruye la vida de
> una tarea; no hay ruta que permita editar o borrar un `Cambio`; límites de tamaño
> respetados.

### Prompt Fase 13
> Implementá la Fase 13: exposición segura. Config del proxy (Caddyfile o `tailscale serve`,
> según lo validado) con la app todavía bindeando 127.0.0.1. Middleware de headers: HSTS,
> X-Content-Type-Options, Referrer-Policy y CSP `default-src 'self'; style-src 'self'
> 'unsafe-inline'`. Para que la CSP no rompa nada, sacá el JS inline: los `onclick` de
> `app/templates/partials/tablero.html` (líneas 78 y 82) y el `<script>` de
> `app/templates/base.html` van a un `.js` vendoreado o se reemplazan por HTMX. Límite de
> tamaño y de cantidad de filas en la subida de planillas, rechazando antes de parsear.
> Backup automático con `VACUUM INTO` y rotación, más `README-OPERACION.md` con levantar,
> actualizar, rotar SECRET_KEY, restaurar backup y dar de baja a un usuario.
> Criterios de aceptación: el puerto de la app no responde desde otra máquina; sin
> advertencias de CSP en la consola del navegador; un backup restaurado en una máquina
> limpia levanta la app con los datos; corré `/security-review` sobre el diff completo del
> bloque A y resolvé lo que salga.

### Prompt Fase 14
> Implementá la Fase 14: línea base. Modelos `LineaBase` (proyecto, nombre, fecha, quién,
> vigente) y `LineaBaseTarea` (task_id, inicio, fin, duración, ámbito congelados) en
> `app/models_base.py`. `app/engine/comparar.py` en Python puro, sin FastAPI ni SQLModel:
> recibe el cronograma actual y el congelado y devuelve el desvío en días hábiles con signo
> por tarea, más agregados por ámbito. Service para congelar, listar y marcar vigente (solo
> el dueño). Columna **Desvío** en la grilla y barra base en gris debajo de la actual en el
> Gantt.
> Criterios de aceptación: tests del engine sin DB para tarea atrasada, adelantada, sin
> cambios, tarea nueva que no estaba en la base y tarea de la base que ya no existe;
> congelar no cambia ninguna fecha del cronograma vivo; un proyecto sin línea base funciona
> igual y no muestra desvíos vacíos; límites de tamaño respetados.

### Prompt Fase 15
> Implementá la Fase 15: avance real. `Task` gana `avance` (0-100), `inicio_real` y
> `fin_real`. El % pasa a ser la fuente de verdad y `estado` se deriva (0 pendiente, 1-99 en
> curso, 100 hecha) para que no puedan contradecirse; escribí la migración de datos que
> traduce los estados actuales y actualizá todo el código que hoy lee `estado`. La grilla
> edita el % en la celda. Sumá al resumen el **avance planificado a la fecha de corte**,
> calculado contra la línea base vigente, junto al avance real.
> Criterios de aceptación: tests del avance planificado (proyecto sin empezar, a mitad de
> camino, terminado, y sin línea base); una tarea al 100% sin `fin_real` lo toma del
> cronograma; ninguna base existente pierde el estado de sus tareas al migrar; resumen y
> Gantt siguen coherentes.

### Prompt Fase 16
> Implementá la Fase 16: el informe. Ruta `/proyectos/{id}/informe?corte=YYYY-MM-DD`
> accesible desde rol lector para arriba. `app/services/informe.py` arma el DTO —datos, no
> HTML— con: portada, resumen ejecutivo (ventana por ámbito, avance real vs planificado,
> desvío contra la base, próximo hito), tareas atrasadas y en riesgo (sin holgura y con
> desvío), hitos con fecha base y proyectada, qué se movió desde el informe anterior usando
> la auditoría de la Fase 12, y el Gantt. Plantillas en `templates/informe/` con CSS
> `@media print` para A4 y saltos de página controlados. Export a Excel con openpyxl: grilla
> completa con fechas base, actuales y desvío.
> Criterios de aceptación: test que compara los números del informe con los de la grilla
> sobre el mismo proyecto y exige que coincidan; el PDF impreso desde el navegador entra en
> A4 sin cortar barras ni tablas; el Excel abre sin advertencias; `services/informe.py` no
> genera HTML; límites de tamaño respetados.

## Cambios a CLAUDE.md

La sección **Seguridad** de CLAUDE.md hoy dice que la app bindea solo `127.0.0.1` y que
exponerla exige auth + HTTPS previos. Esa regla no se toca ahora: **se cumple recién al
cerrar la Fase 13**, y ahí se reescribe la sección así (esto es el texto a aplicar en esa
fase, no antes):

> - La app **sigue bindeando solo `127.0.0.1`**: el TLS lo termina el proxy de adelante, y
>   el proceso Python nunca escucha en una interfaz pública.
> - **Ninguna consulta parte de un id crudo.** Toda ruta de proyecto pasa por
>   `exige_lector/editor/dueño`, que resuelve entidad y permiso juntos y responde 404 —no
>   403— ante un no-miembro. Esconder el botón en la UI no es un control.
> - Contraseñas con **argon2id**, nunca en logs ni en respuestas. Sesiones como fila en la
>   DB, con token opaco, revocables, que rotan al iniciar sesión.
> - **Todo verbo que no sea GET exige token CSRF válido.**
> - `SECRET_KEY` por variable de entorno; la app no arranca en modo no-debug sin ella.
> - El resto sigue vigente: Pydantic en el borde, el grafo tratado como input hostil, ORM
>   sin SQL a mano, autoescape sin `|safe`, sin secretos en el repo, sin stack traces al
>   navegador, la DB fuera de git.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| **Exponer la app con el bloque A a medio hacer.** Es el riesgo más grave del plan y el más fácil de cometer: alcanza con querer mostrarle algo a alguien un martes. | El orden de fases es la mitigación, y la Fase 13 es una puerta explícita: hasta que no cierre, la URL no se comparte con nadie. Escrito acá para que no dependa de acordarse. |
| **IDOR.** Con ids secuenciales en la URL, el modo de falla más probable no es un hacker: es un miembro cambiando un número y viendo el proyecto de otro cliente. | Fase 11 revisa *todas* las rutas existentes, y el criterio de hecho exige un test por verbo, no una inspección visual. |
| **Pérdida silenciosa de ediciones** entre dos personas. Rompe la confianza en la herramienta más rápido que cualquier bug de cálculo, y sin dejar rastro. | Bloqueo optimista con 409 visible (Fase 12) en vez de last-write-wins, más auditoría para reconstruir qué pasó. |
| **La migración de `estado` a `avance` toca datos ajenos.** En v1 un error de migración te costaba tu propia base; ahora cuesta el trabajo de otros. | Alembic desde la Fase 10, backup probado antes (Fase 13 va antes que la 15 a propósito), y la migración con test sobre una base poblada. |
| **El informe miente.** Si sus números no coinciden con la grilla, el daño es peor que no tener informe: se manda a un cliente. | Criterio de hecho de la Fase 16: un test compara ambas salidas sobre el mismo proyecto y exige coincidencia. |
| **Un escritor por vez en SQLite.** | Aceptado para decenas de usuarios. El síntoma a vigilar está nombrado (esperas al guardar) y el upgrade a Postgres está documentado como decisión ya tomada, no como investigación pendiente. |
| **Backup que nunca se probó.** Un backup no restaurado es una carpeta que ocupa disco. | El criterio de hecho de la Fase 13 no es "el backup corre": es "se restauró en una máquina limpia y la app levantó". |
