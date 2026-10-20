BEGIN;
-- Unifica posibles registros creados con el nombre temporal REALIZADA.
UPDATE sesion_clase
SET estado = 'IMPARTIDA'
WHERE estado = 'REALIZADA';
-- Sustituye la regla anterior por los estados definitivos.
ALTER TABLE sesion_clase DROP CONSTRAINT IF EXISTS ck_sesion_estado;
ALTER TABLE sesion_clase
ADD CONSTRAINT ck_sesion_estado CHECK (
        estado IN (
            'PROGRAMADA',
            'IMPARTIDA',
            'SUSPENDIDA',
            'CANCELADA'
        )
    );
COMMIT;
SELECT id_sesion,
    id_curso,
    numero_clase,
    fecha,
    estado
FROM sesion_clase
ORDER BY id_curso,
    numero_clase;
