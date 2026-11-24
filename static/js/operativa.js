/* Mejora progresiva F8.3. Ningún total calculado aquí se envía al servidor. */
(() => {
  const moneda = n => `USD ${(n / 100).toFixed(2)}`;
  const centavos = texto => {
    const t = String(texto || '').trim().replace(',', '.');
    if (!t) return 0;
    if (!/^\d{1,8}(\.\d{1,2})?$/.test(t)) return null;
    const [entero, decimal = ''] = t.split('.');
    return Number(entero) * 100 + Number(decimal.padEnd(2, '0'));
  };
  const sumar = campos => {
    const valores = [...campos].map(c => centavos(c.value));
    return valores.includes(null) ? null : valores.reduce((a, b) => a + b, 0);
  };
  document.querySelectorAll('.f83-form').forEach(form => {
    // La selección original conserva nombres, valores y validaciones. La búsqueda es opcional.
    form.querySelectorAll('select').forEach(select => {
      if (select.disabled || select.multiple || select.options.length < 8) return;
      const bloque = document.createElement('div'); bloque.className = 'f83-filtro-select';
      const etiqueta = document.createElement('label');
      const buscar = document.createElement('input'); buscar.type = 'search';
      buscar.id = `${select.id}-buscar`; etiqueta.htmlFor = buscar.id;
      etiqueta.textContent = `Buscar en ${form.querySelector(`label[for="${select.id}"]`)?.textContent.replace('*', '').trim() || 'la selección'}`;
      const salida = document.createElement('small'); salida.setAttribute('role', 'status');
      const opciones = [...select.options].map(o => o.cloneNode(true));
      buscar.addEventListener('input', () => {
        const texto = buscar.value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
        const elegido = select.value;
        const visibles = opciones.filter(o => !o.value || o.value === elegido || o.textContent.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().includes(texto));
        select.replaceChildren(...visibles.map(o => o.cloneNode(true))); select.value = elegido;
        salida.textContent = `${visibles.filter(o => o.value).length} opciones. La selección actual se conserva.`;
      });
      bloque.append(etiqueta, buscar, salida); select.before(bloque);
    });
    const revision = form.querySelector('[data-confirmacion-pago]');
    const enviar = form.querySelector('button[type=submit]');
    let revisado = false;
    function pago() {
      const importes = form.querySelectorAll('[name^="importe_"]');
      const total = sumar(importes), saldo = centavos(form.dataset.saldo);
      const salida = form.querySelector('[data-resumen-pago]');
      if (!salida) return;
      const metodo = form.querySelector('[name=metodo]');
      salida.textContent = total === null ? 'Revise los importes: use como máximo dos decimales.' :
        `Total a cobrar: ${moneda(total)}. Saldo financiero restante estimado: ${moneda(saldo - total)}. Método: ${metodo.selectedOptions[0].textContent}.`;
      form.querySelectorAll('[data-pago-fila]').forEach(fila => {
        const importe = centavos(fila.querySelector('[name^="importe_"]').value);
        const parte = centavos(fila.dataset.parte);
        let aviso = '';
        if (importe) {
          if (fila.dataset.convenio === 'si') aviso = 'Use el cobro del convenio; el servidor rechazará este cobro ordinario.';
          else if (importe > parte) aviso = 'El importe supera la parte disponible para este cobro. Revise saldo y padrinazgo.';
          else if (fila.dataset.abonos === 'no' && importe !== parte) aviso = `Este concepto exige pagar la parte completa: ${moneda(parte)}.`;
        }
        fila.querySelector('[data-aviso-importe]').textContent = aviso;
      });
      if (revision) revision.querySelector('[data-confirmacion-texto]').textContent = salida.textContent;
    }
    function actualizar() {
      revisado = false;
      if (revision) revision.hidden = true;
      if (form.hasAttribute('data-pago-form')) pago();
      const abono = form.querySelector('[data-resumen-abono]');
      if (abono) {
        const cuotas = sumar(form.querySelectorAll('[name^="cuota_"]'));
        const obligaciones = sumar(form.querySelectorAll('[name^="obligacion_"]'));
        abono.textContent = cuotas === null || obligaciones === null ? 'Revise los decimales de los importes.' :
          `Abono por cuotas: ${moneda(cuotas)}. Desglose por obligaciones: ${moneda(obligaciones)}. Diferencia: ${moneda(cuotas - obligaciones)}. Ambas sumas deben coincidir; no se suman como dos cobros.`;
      }
      const plan = form.querySelector('[data-resumen-cuotas]');
      if (plan) {
        const total = sumar(form.querySelectorAll('[name^="cuotas-"][name$="-monto"]'));
        plan.textContent = total === null ? 'Revise los importes de las cuotas.' : `Suma de cuotas propuestas: ${moneda(total)}. Debe coincidir con el saldo de las obligaciones seleccionadas, que verifica el servidor.`;
      }
    }
    form.addEventListener('input', actualizar); form.addEventListener('change', actualizar); actualizar();
    revision?.querySelector('[data-confirmar-pago]').addEventListener('click', () => { revisado = true; form.requestSubmit(enviar); });
    revision?.querySelector('[data-volver-pago]').addEventListener('click', () => { revisado = false; revision.hidden = true; form.querySelector('[name^="importe_"]')?.focus(); });
    form.addEventListener('submit', event => {
      if (form.dataset.enviando === 'si') { event.preventDefault(); return; }
      if (revision && !revisado) { event.preventDefault(); pago(); revision.hidden = false; revision.focus(); return; }
      form.dataset.enviando = 'si'; form.setAttribute('aria-busy', 'true');
      const salida = form.querySelector('[data-estado-envio]');
      if (salida) salida.textContent = 'Enviando. Espere el resultado; no vuelva a pulsar.';
      // No deshabilitar botones ni campos: se conservan accion/paso, tokens y claves originales.
    });
  });
  document.querySelectorAll('[data-matricula-form]').forEach(form => {
    const select = form.querySelector('[name=ciclo]');
    const mostrar = () => form.querySelectorAll('[data-ciclo]').forEach(d => {
      d.hidden = Boolean(select.value && d.dataset.ciclo !== select.value);
      d.open = d.dataset.ciclo === select.value;
    });
    select.addEventListener('change', mostrar); mostrar();
  });
  window.addEventListener('pageshow', () => document.querySelectorAll('.f83-form').forEach(f => { delete f.dataset.enviando; f.removeAttribute('aria-busy'); const s=f.querySelector('[data-estado-envio]'); if(s)s.textContent=''; }));
  document.querySelector('[data-errores]')?.focus();
})();
