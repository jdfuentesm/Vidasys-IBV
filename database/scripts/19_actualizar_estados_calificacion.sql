BEGIN;
ALTER TABLE public.calificacion DROP CONSTRAINT IF EXISTS ck_calificacion_estado;
ALTER TABLE public.calificacion
ADD CONSTRAINT ck_calificacion_estado CHECK (
        estado IN (
            'PENDIENTE',
            'APROBADA',
            'REPROBADA_ACADEMICAMENTE'
        )
    );
COMMIT;
SELECT conname,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'ck_calificacion_estado';
