
CREATE OR REPLACE VIEW vw_estado_cuenta_estudiante AS
SELECT
    e.id_estudiante,
    e.codigo_estudiante,
    e.nombres,
    e.apellidos,

    m.id_matricula,
    m.numero_matricula,

    o.id_obligacion,
    cc.nombre AS concepto,
    o.descripcion,
    o.fecha_emision,
    o.fecha_vencimiento,
    o.monto_original,
    o.monto_descuento,
    o.monto_final,

    COALESCE(pagos.total_pagado, 0) AS total_pagado,
    COALESCE(donaciones.total_donado, 0) AS total_donado,

    GREATEST(
        o.monto_final
        - COALESCE(pagos.total_pagado, 0)
        - COALESCE(donaciones.total_donado, 0),
        0
    ) AS saldo_pendiente,

    o.estado AS estado_obligacion,

    CASE
        WHEN estudiante_esta_solvente(e.id_estudiante)
            THEN 'SOLVENTE'
        ELSE 'INSOLVENTE'
    END AS solvencia_actual

FROM estudiante e

INNER JOIN matricula m
    ON m.id_estudiante = e.id_estudiante

INNER JOIN obligacion o
    ON o.id_matricula = m.id_matricula

INNER JOIN concepto_cobro cc
    ON cc.id_concepto = o.id_concepto

LEFT JOIN LATERAL (
    SELECT SUM(dp.monto_aplicado) AS total_pagado
    FROM detalle_pago dp
    INNER JOIN pago p
        ON p.id_pago = dp.id_pago
    WHERE dp.id_obligacion = o.id_obligacion
      AND p.estado = 'REGISTRADO'
) pagos ON TRUE

LEFT JOIN LATERAL (
    SELECT SUM(d.monto) AS total_donado
    FROM donacion d
    WHERE d.id_obligacion = o.id_obligacion
      AND d.estado = 'RECIBIDA'
) donaciones ON TRUE;