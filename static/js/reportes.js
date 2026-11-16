document.querySelectorAll('[data-imprimir-reporte]').forEach(boton => {
    boton.addEventListener('click', () => window.print());
});
