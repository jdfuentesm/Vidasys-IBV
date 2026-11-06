(() => {
    const formulario = document.getElementById('asistencia');
    if (!formulario) return;
    let pendiente = formulario.dataset.unsaved === 'true';
    formulario.addEventListener('input', () => {
        pendiente = true;
        formulario.dataset.unsaved = 'true';
        document.getElementById('estado-asistencia').textContent = 'Tiene cambios sin guardar. Pulse Guardar asistencia para confirmarlos.';
    });
    formulario.addEventListener('submit', () => { pendiente = false; });
    document.querySelectorAll('[data-seleccion]').forEach(seleccion => {
        seleccion.addEventListener('submit', event => {
            if (pendiente && !window.confirm('Hay cambios sin guardar. ¿Desea salir de esta sesión sin guardarlos?')) event.preventDefault();
            else pendiente = false;
        });
    });
    window.addEventListener('beforeunload', event => {
        if (pendiente) { event.preventDefault(); event.returnValue = ''; }
    });
})();
