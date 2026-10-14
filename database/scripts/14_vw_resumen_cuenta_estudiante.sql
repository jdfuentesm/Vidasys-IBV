CREATE OR REPLACE VIEW vw_resumen_cuenta_estudiante AS
SELECT
    id_estudiante,
    codigo_estudiante,
    nombres,
    apellidos,
    COUNT(id_obligacion) AS total_obligaciones,
    SUM(monto_final) AS total_cargado,
    SUM(total_pagado) AS total_pagado,
    SUM(total_donado) AS total_donado,
    SUM(saldo_pendiente) AS saldo_pendiente,
    COUNT(*) FILTER (
        WHERE estado_obligacion = 'VENCIDA'
    ) AS obligaciones_vencidas,
    MAX(solvencia_actual) AS solvencia_actual
FROM vw_estado_cuenta_estudiante
GROUP BY
    id_estudiante,
    codigo_estudiante,
    nombres,
    apellidos;