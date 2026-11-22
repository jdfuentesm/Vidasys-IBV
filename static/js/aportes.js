/* Solo orientación visual: el servidor recalcula y valida cada centavo. */
document.querySelectorAll('[data-aportes-form]').forEach(form => {
  const salida=form.querySelector('[data-resumen-aporte]');
  function calcular(){
    let total=0;
    const porcentaje=form.querySelector('[name=modalidad]')?.value==='PORCENTAJE';
    const pct=Number(form.querySelector('[name=porcentaje]')?.value||0);
    form.querySelectorAll('[data-aporte]').forEach(input=>{
      const pk=input.name.replace('aporte_','');
      const seleccionado=form.querySelector(`[data-seleccion="${pk}"]`)?.checked;
      const valor=porcentaje?(seleccionado?Number(input.dataset.saldo)*pct/100:0):Number(input.value||0);
      total+=Number.isFinite(valor)?valor:0;
    });
    const recibido=form.querySelector('[name=monto]');
    salida.textContent=`Total a aplicar o comprometer: USD ${total.toFixed(2)}.`+(recibido?` Dinero recibido: USD ${Number(recibido.value||0).toFixed(2)}. Diferencia del desglose: USD ${(Number(recibido.value||0)-total).toFixed(2)}.`:' Un compromiso no registra dinero en caja.');
  }
  const compromiso=form.querySelector('[name=solicitud]');
  compromiso?.addEventListener('change',()=>{const donante=compromiso.selectedOptions[0]?.dataset.donante;if(donante){form.querySelector('[name=donante]').value=donante;form.querySelector('[name=modalidad]').value='PADRINAZGO';}calcular();});
  form.addEventListener('input',calcular);form.addEventListener('change',calcular);calcular();
});
