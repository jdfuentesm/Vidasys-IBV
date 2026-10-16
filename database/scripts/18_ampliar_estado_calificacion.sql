BEGIN;
ALTER TABLE public.calificacion
ALTER COLUMN estado TYPE VARCHAR(30);
COMMIT;
SELECT column_name,
    data_type,
    character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'public'
    AND table_name = 'calificacion'
    AND column_name = 'estado';
