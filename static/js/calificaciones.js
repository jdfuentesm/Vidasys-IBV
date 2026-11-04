/* La vista previa usa el cálculo del servidor, sin duplicar la fórmula académica. */
(() => {
    const libro = document.getElementById('libro');
    if (!libro) return;
    const estado = document.getElementById('estado-guardado');
    let pendiente = libro.dataset.unsaved === 'true';
    let temporizador;
    let solicitud;
    let secuencia = 0;
    libro.addEventListener('input', () => {
        pendiente = true;
        estado.textContent = 'Tiene cambios sin guardar. Calculando vista previa…';
        clearTimeout(temporizador);
        if (solicitud) solicitud.abort();
        const actual = ++secuencia;
        temporizador = setTimeout(async () => {
            solicitud = new AbortController();
            const datos = new FormData(libro);
            datos.set('accion', 'calcular');
            try {
                const respuesta = await fetch(libro.dataset.previewUrl, {
                    method: 'POST', body: datos, signal: solicitud.signal,
                    credentials: 'same-origin', headers: {'Accept': 'application/json'}
                });
                if (!respuesta.ok) throw new Error('No disponible');
                const resultado = await respuesta.json();
                if (actual !== secuencia) return;
                for (const fila of resultado.filas) {
                    const elemento = libro.querySelector(`[data-inscripcion="${fila.id}"]`);
                    if (!elemento) continue;
                    elemento.querySelector('[data-nota]').textContent = fila.nota;
                    elemento.querySelector('[data-estado]').textContent = fila.estado;
                }
                estado.textContent = 'Vista previa calculada. Pulse Guardar todas las calificaciones para confirmar.';
            } catch (error) {
                if (error.name !== 'AbortError') estado.textContent = 'Cambios sin guardar. La vista previa no está disponible; el cálculo se realizará al guardar.';
            }
        }, 500);
    });
    libro.addEventListener('submit', () => {
        pendiente = false;
        clearTimeout(temporizador);
        if (solicitud) solicitud.abort();
    });
    document.getElementById('seleccion-curso').addEventListener('submit', event => {
        if (pendiente && !window.confirm('Tiene cambios sin guardar. ¿Desea cambiar de curso y dejarlos sin guardar?')) event.preventDefault();
        else pendiente = false;
    });
    window.addEventListener('beforeunload', event => {
        if (pendiente) { event.preventDefault(); event.returnValue = ''; }
    });
})();
