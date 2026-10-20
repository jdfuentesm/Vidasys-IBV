-- ============================================================
-- VidaSYS-IBV
-- Script 22: Sesiones ordinarias y extraordinarias
-- Clases 1 a 6: ordinarias
-- Clases 7 y 8: extraordinarias con autorización de directora
-- ============================================================
BEGIN;
ALTER TABLE sesion_clase
ADD COLUMN IF NOT EXISTS es_extraordinaria BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE sesion_clase
ADD COLUMN IF NOT EXISTS motivo_extension TEXT;
ALTER TABLE sesion_clase
ADD COLUMN IF NOT EXISTS id_usuario_autoriza BIGINT;
ALTER TABLE sesion_clase
ADD COLUMN IF NOT EXISTS fecha_autorizacion TIMESTAMPTZ;
-- Relación con la usuaria que autoriza.
ALTER TABLE sesion_clase DROP CONSTRAINT IF EXISTS fk_sesion_usuario_autoriza;
ALTER TABLE sesion_clase
ADD CONSTRAINT fk_sesion_usuario_autoriza FOREIGN KEY (id_usuario_autoriza) REFERENCES usuario(id_usuario) ON DELETE RESTRICT;
-- Solo se permiten clases numeradas del 1 al 8.
ALTER TABLE sesion_clase DROP CONSTRAINT IF EXISTS ck_sesion_numero_clase;
ALTER TABLE sesion_clase
ADD CONSTRAINT ck_sesion_numero_clase CHECK (
        numero_clase BETWEEN 1 AND 8
    );
-- Las clases 7 y 8 requieren autorización y justificación.
ALTER TABLE sesion_clase DROP CONSTRAINT IF EXISTS ck_sesion_extension_autorizada;
ALTER TABLE sesion_clase
ADD CONSTRAINT ck_sesion_extension_autorizada CHECK (
        (
            numero_clase BETWEEN 1 AND 6
            AND es_extraordinaria = FALSE
        )
        OR (
            numero_clase BETWEEN 7 AND 8
            AND es_extraordinaria = TRUE
            AND id_usuario_autoriza IS NOT NULL
            AND fecha_autorizacion IS NOT NULL
            AND NULLIF(BTRIM(motivo_extension), '') IS NOT NULL
        )
    );
COMMIT;
-- Comprobación de las sesiones existentes
SELECT id_sesion,
    id_curso,
    numero_clase,
    fecha,
    estado,
    es_extraordinaria,
    motivo_extension,
    id_usuario_autoriza,
    fecha_autorizacion
FROM sesion_clase
ORDER BY id_curso,
    numero_clase;
