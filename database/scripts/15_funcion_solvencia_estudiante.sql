CREATE OR REPLACE FUNCTION estudiante_esta_solvente(
    p_id_estudiante BIGINT,
    p_fecha DATE DEFAULT CURRENT_DATE
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    -- Verificamos que el estudiante exista.
    IF NOT EXISTS (
        SELECT 1
        FROM estudiante
        WHERE id_estudiante = p_id_estudiante
    ) THEN
        RAISE EXCEPTION
            'No existe el estudiante con id %',
            p_id_estudiante;
    END IF;

    /*
     * PRIMERA REGLA:
     * Una obligación vencida con saldo vuelve insolvente
     * al estudiante, salvo que esté cubierta por un
     * convenio activo o cumplido.
     */
    IF EXISTS (
        SELECT 1
        FROM obligacion o
        INNER JOIN matricula m
            ON m.id_matricula = o.id_matricula
        WHERE m.id_estudiante = p_id_estudiante
          AND o.estado <> 'ANULADA'
          AND p_fecha > o.fecha_vencimiento

          AND o.monto_final >
              COALESCE((
                  SELECT SUM(dp.monto_aplicado)
                  FROM detalle_pago dp
                  INNER JOIN pago p
                      ON p.id_pago = dp.id_pago
                  WHERE dp.id_obligacion = o.id_obligacion
                    AND p.estado = 'REGISTRADO'
              ), 0)
              +
              COALESCE((
                  SELECT SUM(d.monto)
                  FROM donacion d
                  WHERE d.id_obligacion = o.id_obligacion
                    AND d.estado = 'RECIBIDA'
              ), 0)

          AND NOT EXISTS (
              SELECT 1
              FROM convenio_obligacion co
              INNER JOIN convenio_pago cp
                  ON cp.id_convenio = co.id_convenio
              WHERE co.id_obligacion = o.id_obligacion
                AND cp.estado IN ('ACTIVO', 'CUMPLIDO')
          )
    ) THEN
        RETURN FALSE;
    END IF;

    /*
     * SEGUNDA REGLA:
     * Un convenio marcado formalmente como incumplido
     * vuelve insolvente al estudiante.
     */
    IF EXISTS (
        SELECT 1
        FROM convenio_pago cp
        WHERE cp.id_estudiante = p_id_estudiante
          AND cp.estado = 'INCUMPLIDO'
    ) THEN
        RETURN FALSE;
    END IF;

    /*
     * TERCERA REGLA:
     * Una cuota vencida y todavía no cubierta dentro
     * de un convenio activo vuelve insolvente al alumno.
     */
    IF EXISTS (
        SELECT 1
        FROM cuota_convenio cc
        INNER JOIN convenio_pago cp
            ON cp.id_convenio = cc.id_convenio
        WHERE cp.id_estudiante = p_id_estudiante
          AND cp.estado = 'ACTIVO'
          AND cc.estado <> 'ANULADA'
          AND p_fecha > cc.fecha_vencimiento

          AND cc.monto_cuota >
              COALESCE((
                  SELECT SUM(apc.monto_aplicado)
                  FROM aplicacion_pago_cuota apc
                  INNER JOIN pago p
                      ON p.id_pago = apc.id_pago
                  WHERE apc.id_cuota = cc.id_cuota
                    AND p.estado = 'REGISTRADO'
              ), 0)
    ) THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;
END;
$$;