-- SOLO para un esquema NUEVO de demostración. No reemplaza la función de la base real.
-- Saldo conforme a vw_estado_cuenta_estudiante (SQL 17).
CREATE FUNCTION recalcular_estado_obligacion(p_id BIGINT) RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE v RECORD;
BEGIN
    SELECT o.estado, o.fecha_vencimiento, c.saldo_pendiente, c.total_pagado, c.total_donado
      INTO v FROM obligacion o JOIN vw_estado_cuenta_estudiante c USING (id_obligacion)
      WHERE o.id_obligacion=p_id FOR UPDATE OF o;
    IF NOT FOUND OR v.estado='ANULADA' THEN RETURN; END IF;
    UPDATE obligacion SET estado=CASE
      WHEN v.saldo_pendiente <= 0 THEN 'PAGADA'
      WHEN v.fecha_vencimiento < CURRENT_DATE THEN 'VENCIDA'
      WHEN v.total_pagado + v.total_donado > 0 THEN 'PARCIAL'
      ELSE 'PENDIENTE' END WHERE id_obligacion=p_id;
END; $$;

CREATE FUNCTION demo_actualizar_pago() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v BIGINT;
BEGIN
    FOR v IN SELECT id_obligacion FROM detalle_pago WHERE id_pago=NEW.id_pago ORDER BY id_obligacion LOOP
        PERFORM recalcular_estado_obligacion(v);
    END LOOP;
    RETURN NEW;
END; $$;
CREATE TRIGGER demo_estado_pago AFTER UPDATE OF estado ON pago
  FOR EACH ROW EXECUTE FUNCTION demo_actualizar_pago();
