/* Comportamiento de la grilla. Vendoreado, sin dependencias y sin CDN.
 *
 * Dos cosas, las dos porque HTMX solo no alcanza:
 *
 * 1. Columnas redimensionables arrastrando el borde, como en una planilla. El ancho
 *    se guarda por proyecto en localStorage: es preferencia de pantalla, no dato del
 *    proyecto, y mandarla al servidor en cada píxel de arrastre sería absurdo.
 * 2. Devolver el foco a la celda que estabas editando. Cada cambio recalcula el
 *    cronograma entero y repinta la grilla, así que sin esto perdés el cursor en
 *    cada tecla.
 *
 * Todo se re-aplica después de cada swap de HTMX, porque el panel se vuelve a
 * dibujar entero.
 */
(function () {
  'use strict';

  var MINIMO = 40;
  var MAXIMO = 900;

  function panel() {
    return document.querySelector('.panel-izq');
  }

  function clave() {
    var m = window.location.pathname.match(/\/proyectos\/(\d+)/);
    return m ? 'wopr.anchos.' + m[1] : null;
  }

  function guardados() {
    try {
      return JSON.parse(localStorage.getItem(clave()) || '{}');
    } catch (e) {
      return {};
    }
  }

  function guardar(anchos) {
    try {
      localStorage.setItem(clave(), JSON.stringify(anchos));
    } catch (e) {
      /* Sin localStorage (modo privado, cuota llena) la grilla sigue andando:
         se pierde la preferencia, no la funcionalidad. */
    }
  }

  function aplicar() {
    var caja = panel();
    if (!caja) return;
    var anchos = guardados();
    Object.keys(anchos).forEach(function (col) {
      caja.style.setProperty('--w-' + col, anchos[col] + 'px');
    });
  }

  function restablecer() {
    var caja = panel();
    if (caja) {
      Object.keys(guardados()).forEach(function (col) {
        caja.style.removeProperty('--w-' + col);
      });
    }
    guardar({});
  }

  /* Arrastre. Se escucha en el documento y no en cada tirador: la grilla se repinta
     en cada edición y volver a enganchar oyentes en cada swap se olvida una vez y
     deja de andar en silencio. */
  document.addEventListener('pointerdown', function (evento) {
    var tirador = evento.target.closest('.tirador');
    if (!tirador) return;

    var cabecera = tirador.closest('[data-col]');
    var caja = panel();
    if (!cabecera || !caja) return;

    var col = cabecera.dataset.col;
    var desde = evento.clientX;
    var inicial = cabecera.getBoundingClientRect().width;
    var actual = inicial;

    evento.preventDefault();
    tirador.setPointerCapture(evento.pointerId);
    document.body.classList.add('redimensionando');

    function mover(e) {
      actual = Math.max(MINIMO, Math.min(MAXIMO, inicial + (e.clientX - desde)));
      caja.style.setProperty('--w-' + col, actual + 'px');
    }

    function soltar() {
      tirador.removeEventListener('pointermove', mover);
      tirador.removeEventListener('pointerup', soltar);
      tirador.removeEventListener('pointercancel', soltar);
      document.body.classList.remove('redimensionando');
      var anchos = guardados();
      anchos[col] = Math.round(actual);
      guardar(anchos);
    }

    tirador.addEventListener('pointermove', mover);
    tirador.addEventListener('pointerup', soltar);
    /* Sin esto, un gesto cancelado (touch, cambio de ventana) deja el arrastre
       enganchado y el próximo hover redimensiona sin apretar nada. */
    tirador.addEventListener('pointercancel', soltar);
  });

  /* Doble clic en el tirador: esa columna vuelve al ancho que calcula el servidor. */
  document.addEventListener('dblclick', function (evento) {
    var tirador = evento.target.closest('.tirador');
    if (!tirador) return;
    var cabecera = tirador.closest('[data-col]');
    var caja = panel();
    if (!cabecera || !caja) return;
    caja.style.removeProperty('--w-' + cabecera.dataset.col);
    var anchos = guardados();
    delete anchos[cabecera.dataset.col];
    guardar(anchos);
  });

  document.addEventListener('click', function (evento) {
    if (evento.target.closest('[data-accion="anchos-por-defecto"]')) {
      evento.preventDefault();
      restablecer();
    }
    var alterna = evento.target.closest('[data-alterna]');
    if (alterna) {
      var destino = document.getElementById(alterna.dataset.alterna);
      if (destino) destino.classList.toggle('oculto');
    }
  });

  /* Confirmación de formularios de borrado. El texto viene entero del servidor en
     data-confirmar: un nombre interpolado dentro de JS inline es XSS aunque el HTML
     esté escapado (el navegador decodifica las entidades antes de evaluar). */
  document.addEventListener('submit', function (evento) {
    var form = evento.target.closest('form[data-confirmar]');
    if (form && !window.confirm(form.dataset.confirmar)) {
      evento.preventDefault();
    }
  });

  /* Foco: se recuerda antes del swap y se devuelve después. */
  var ultimaCelda = null;
  document.addEventListener('htmx:beforeSwap', function () {
    ultimaCelda = document.activeElement && document.activeElement.id;
  });
  document.addEventListener('htmx:afterSwap', function () {
    aplicar();
    var celda = ultimaCelda && document.getElementById(ultimaCelda);
    if (celda) {
      celda.focus();
      if (celda.select) celda.select();
    }
  });

  document.addEventListener('DOMContentLoaded', aplicar);
})();
