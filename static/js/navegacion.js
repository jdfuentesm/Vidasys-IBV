/* F8.1: navegación progresiva. No altera formularios ni ejecuta operaciones. */
(() => {
    const boton = document.querySelector('.nav-toggle');
    const menu = document.getElementById('menu-app');
    const movil = window.matchMedia('(max-width: 1000px)');
    if (boton && menu) {
        document.documentElement.classList.add('js');
        let ultimoFoco = document.activeElement;
        document.addEventListener('focusin', event => {
            if (event.target !== document.body) ultimoFoco = event.target;
        });
        const cambiar = (abierto, enfocar = false) => {
            menu.dataset.abierto = String(abierto);
            boton.setAttribute('aria-expanded', String(abierto));
            boton.textContent = abierto ? 'Cerrar menú' : 'Menú';
            if (abierto && enfocar) menu.querySelector('a')?.focus();
        };
        boton.addEventListener('click', () => cambiar(menu.dataset.abierto !== 'true', true));
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && movil.matches && menu.dataset.abierto === 'true') {
                cambiar(false);
                boton.focus();
            }
        });
        menu.addEventListener('click', event => {
            if (movil.matches && event.target.closest('a')) cambiar(false);
        });
        movil.addEventListener('change', () => {
            // El navegador puede desenfocar un control al ocultarlo por media query.
            const foco = document.activeElement === document.body ? ultimoFoco : document.activeElement;
            const dentro = menu.contains(foco);
            const enBoton = foco === boton;
            cambiar(false);
            if (movil.matches && dentro) boton.focus();
            if (!movil.matches && enBoton) menu.querySelector('a')?.focus();
        });
    }
    // Criterios impresos completos; restaurar después el estado que eligió el usuario.
    let ayudas = [];
    window.addEventListener('beforeprint', () => {
        ayudas = [...document.querySelectorAll('[data-ayuda-impresion]')].map(el => [el, el.open]);
        ayudas.forEach(([el]) => { el.open = true; });
    });
    window.addEventListener('afterprint', () => {
        ayudas.forEach(([el, abierto]) => { el.open = abierto; });
        ayudas = [];
    });
})();
