CREATE OR REPLACE FUNCTION actualizar_estados_obligaciones()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_obligacion RECORD;
    v_total_actualizadas INTEGER := 0;
BEGIN
    FOR v_obligacion IN
        SELECT id_obligacion
        FROM obligacion
        WHERE estado NOT IN ('ANULADA', 'EN_CONVENIO')
    LOOP
        PERFORM recalcular_estado_obligacion(
            v_obligacion.id_obligacion
        );

        v_total_actualizadas := v_total_actualizadas + 1;
    END LOOP;

    RETURN v_total_actualizadas;
END;
$$;