DO $$
DECLARE
    v_id_pago           BIGINT;
    v_estado_obligacion VARCHAR(20);
BEGIN
    -- Localizamos el pago registrado de la obligación 3.
    SELECT dp.id_pago
    INTO v_id_pago
    FROM detalle_pago dp
    INNER JOIN pago p
        ON p.id_pago = dp.id_pago
    WHERE dp.id_obligacion = 3
      AND p.estado = 'REGISTRADO'
    ORDER BY dp.id_pago
    LIMIT 1;

    IF v_id_pago IS NULL THEN
        RAISE EXCEPTION
            'No se encontró un pago registrado para la obligación 3';
    END IF;

    -- Anulamos temporalmente el pago.
    UPDATE pago
    SET estado = 'ANULADO'
    WHERE id_pago = v_id_pago;

    SELECT estado
    INTO v_estado_obligacion
    FROM obligacion
    WHERE id_obligacion = 3;

    IF v_estado_obligacion <> 'PARCIAL' THEN
        RAISE EXCEPTION
            'Prueba fallida: se esperaba PARCIAL y se obtuvo %',
            v_estado_obligacion;
    END IF;

    -- Restauramos el pago.
    UPDATE pago
    SET estado = 'REGISTRADO'
    WHERE id_pago = v_id_pago;

    SELECT estado
    INTO v_estado_obligacion
    FROM obligacion
    WHERE id_obligacion = 3;

    IF v_estado_obligacion <> 'PAGADA' THEN
        RAISE EXCEPTION
            'Prueba fallida: se esperaba PAGADA y se obtuvo %',
            v_estado_obligacion;
    END IF;

    RAISE NOTICE
        'Prueba exitosa: pago % ANULADO produjo PARCIAL y REGISTRADO produjo PAGADA',
        v_id_pago;
END;
$$;

SELECT
    p.id_pago,
    p.estado AS estado_pago,
    o.id_obligacion,
    o.estado AS estado_obligacion
FROM pago p
INNER JOIN detalle_pago dp
    ON dp.id_pago = p.id_pago
INNER JOIN obligacion o
    ON o.id_obligacion = dp.id_obligacion
WHERE o.id_obligacion = 3;