/* Un solo DOM y formulario por lote; ampliar nunca copia ni reinicia campos. */
(() => {
  const ancho = window.matchMedia('(min-width: 1000px)');
  const actualizar = () => document.querySelectorAll('[data-componentes]').forEach(d => {
    d.open = ancho.matches || d.hasAttribute('data-con-errores');
  });
  ancho.addEventListener('change', actualizar); actualizar();
  document.querySelector('[data-error-docente]')?.focus();
  const filtro = document.querySelector('[data-filtro-docente]');
  if (filtro) {
    filtro.hidden = false;
    const normal = t => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    filtro.querySelector('input').addEventListener('input', e => {
      const texto = normal(e.target.value).trim(); let visibles = 0;
      document.querySelectorAll('#libro [data-inscripcion]').forEach(fila => {
        fila.hidden = !normal(fila.querySelector('.estudiante').textContent).includes(texto);
        if (!fila.hidden) visibles++;
      });
      filtro.querySelector('[data-conteo-docente]').textContent = `${visibles} estudiantes en la vista. El lote no cambia.`;
    });
  }
  document.querySelectorAll('#libro,#asistencia').forEach(form => {
    form.addEventListener('invalid', event => {
      const fila = event.target.closest('[data-inscripcion]'); if (fila) fila.hidden = false;
      const detalle = event.target.closest('[data-componentes]'); if (detalle) detalle.open = true;
    }, true);
    form.addEventListener('submit', event => {
      if (form.dataset.enviando === 'si') { event.preventDefault(); return; }
      form.dataset.enviando = 'si'; form.setAttribute('aria-busy', 'true');
    });
  });
  window.addEventListener('pageshow', () => document.querySelectorAll('#libro,#asistencia').forEach(f => {
    delete f.dataset.enviando; f.removeAttribute('aria-busy');
  }));
})();
