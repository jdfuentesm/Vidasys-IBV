/* Menú móvil en el flujo de la página: no tapa formularios ni modifica envíos. */
(() => {
    const boton = document.querySelector('.nav-toggle');
    const menu = document.getElementById('menu-app');
    if (!boton || !menu) return;
    document.documentElement.classList.add('js');
    const cambiar = abierto => {
        menu.dataset.abierto = String(abierto);
        boton.setAttribute('aria-expanded', String(abierto));
        boton.textContent = abierto ? 'Cerrar menú' : 'Menú';
    };
    boton.addEventListener('click', () => cambiar(menu.dataset.abierto !== 'true'));
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && menu.dataset.abierto === 'true') {
            cambiar(false);
            boton.focus();
        }
    });
})();
