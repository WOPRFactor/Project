# Para retomar

Nota corta para abrir y saber dónde estamos. El detalle está en `PLAN-DE-OBRA.md` (v1)
y `PLAN-DE-MEJORAS.md` (v2); esto es solo el punto de entrada.

## Levantar la app

En PowerShell, desde la carpeta del proyecto (acordate: `;` y no `&&`):

```powershell
git pull
uv sync
uv run uvicorn app.main:app --reload
```

Después, `http://127.0.0.1:8000`.

## Dónde quedó

Todo lo que funciona con un solo usuario está hecho: **491 tests en verde**, de los
cuales 19 abren un navegador de verdad. El ciclo cierra de punta a punta — cargás o
importás, planificás, congelás lo aprobado, medís el desvío y emitís el informe.

**Los cuatro puntos que habías marcado están cerrados.** Los cuatro, más lo que
apareció al probarlos.

## Lo que se hizo desde tu lista

**1. Encabezados anclados.** La cabecera de la grilla y la fila de semanas quedan fijas
al bajar. Hay un test que scrollea hasta el fondo y las mide.

**2. Riesgos, a fondo.** Dijiste «hacé todo», así que elegí el set estándar y te lo
dejo explícito para que corrijas lo que no te cierre:

- **Respuesta**: evitar / mitigar / transferir / aceptar / escalar. El default es
  *Sin definir* a propósito: poder contar los que nadie decidió es medio registro.
- **Riesgo residual**: P e I *después* del plan. Se declara aparte y **no se calcula**
  —cuánto baja un plan lo estimás vos—. Sin declarar, la app **no supone ninguna
  baja**: el riesgo se dibuja donde está. Hay dos cuadrantes, inherente y residual.
- **Disparador**: qué habría que ver para saber que el riesgo está pasando.
- **Fecha de revisión**, con la vencida marcada en rojo.
- **Tarea del plan**: el riesgo se engancha a la tarea del cronograma que ejecuta la
  respuesta. Si borrás esa tarea, el riesgo queda sin plan enganchado y se avisa.
- **Responsable = persona del proyecto**, igual que en la grilla. Aparece en Equipo.
- **Pendientes del registro**: nueve controles que avisan y **nunca bloquean**
  (materializados, revisión vencida, residual peor que el inherente, sin respuesta,
  respuesta sin plan escrito, sin residual, plan sin efecto, crítico sin revisión,
  crítico sin disparador).
- El informe reporta el residual y el `.xlsx` se lleva el registro en su propia hoja.

*Lo que no hice y es tu llamado:* que un riesgo materializado abra la tarea de impacto
en el cronograma con un clic, y matrices con escala distinta de 5×5.

**3. El selector de columnas anda** — y con él Detalle, Etapa y Color, que estaban
rotos por la misma causa. El `hx-vals` que hace sobrevivir la vista a cada edición
pisaba los valores del formulario que tenía adentro. El formulario salió del
contenedor.

**4. Interruptor de flechas**, al lado de Detalle / Etapa / Color. Apagadas, ni se
calculan.

## Lo primero que conviene mirar

1. **Abrí tu proyecto y mirá el Gantt.** Es lo que estuvimos arreglando y todavía no lo
   viste funcionando.
2. **Entrá a Riesgos.** Es lo más nuevo y lo que más quiero que revises: si la
   respuesta y el residual son los campos que usás, o si te sobra o falta alguno.
3. **Decidí las columnas por defecto.** Hoy vienen Resp., Predec., Días, Inicio, Fin y
   Avance. Si me decís cuáles usás de verdad, achico el default y el título de la tarea
   se ensancha solo. Es cambiar una línea.

## Decisiones que están esperándote

| Qué | Por qué importa |
|---|---|
| **¿Abrimos la app a más gente?** | Es la bifurcación grande. Todo lo que queda del plan (7 fases) necesita usuarios. Hasta que decidas, la app no sale de `127.0.0.1`. |
| **Si la abrimos: ¿Caddy o Tailscale?** | Si los que cargan son solo tu equipo, Tailscale deja **cero puertos abiertos a internet**. Caddy solo si un cliente tiene que entrar a ver el informe. |
| **¿Comentarios y adjuntos ahora?** | Andarían monousuario, pero sin autoría son notas sueltas y archivos sin dueño. Los dejé afuera por eso, no por imposibilidad. Si los querés igual, se hacen. |
| **El ejemplo de Word** | Quedaste en pasármelo para diseñar ese import. Sigue pendiente. |

## Lo que queda del plan (todo necesita usuarios)

- **Bloque A — la puerta de seguridad:** Fase 10 identidad · 11 autorización ·
  12 trabajo simultáneo · 13 exposición segura. **En ese orden y entero** antes de que
  la app salga de localhost.
- **Contenido:** Fase 20 comentarios con categoría y tags · 21 adjuntos.
- **Opcional:** Fase 25, link de solo lectura para que el cliente vea el informe sin
  cuenta.

Afuera del plan: el import desde Word y el asistente con IA que dejaste para después.

## Deudas técnicas conocidas

- Las tres deudas de JS inline que la Fase 13 iba a tener que pagar para poner una CSP
  estricta **ya están saldadas** (todo vive en `static/grilla.js`, vendoreado).
- Los tests de navegador necesitan Chromium: `uv run playwright install chromium`. Sin
  eso se saltean solos y `uv run pytest` sigue andando igual.
- El registro de riesgos **sale** a Excel pero no vuelve: el importador solo entiende
  la hoja del cronograma. Si alguna vez querés cargar riesgos desde una planilla, es
  una fase aparte.
