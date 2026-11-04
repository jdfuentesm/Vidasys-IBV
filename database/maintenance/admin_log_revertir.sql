-- Reversión de metadatos: NO remapea ni borra entradas del historial.
\set ON_ERROR_STOP on
\if :{?identidades_verificadas}
\else
\set identidades_verificadas false
\endif
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
SELECT set_config('vidasys.identidades_verificadas', :'identidades_verificadas', true);
LOCK TABLE public.django_admin_log IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.auth_user IN SHARE MODE;
DO $undo$
DECLARE
    respaldo record;
    actual record;
    columna smallint;
    total integer;
BEGIN
    SELECT * INTO STRICT respaldo FROM public.vidasys_admin_log_fk_backup
    WHERE operacion='admin_log_user_fk_v1';
    SELECT attnum INTO STRICT columna FROM pg_attribute
    WHERE attrelid='public.django_admin_log'::regclass AND attname='user_id' AND NOT attisdropped;
    SELECT count(*) INTO total FROM pg_constraint
    WHERE conrelid='public.django_admin_log'::regclass AND contype='f' AND columna=ANY(conkey);
    IF total<>1 THEN RAISE EXCEPTION 'Número de FK inesperado'; END IF;
    SELECT * INTO STRICT actual FROM pg_constraint
    WHERE conrelid='public.django_admin_log'::regclass AND contype='f' AND columna=ANY(conkey);
    IF actual.conname=respaldo.nombre_original AND pg_get_constraintdef(actual.oid)=respaldo.definicion_original THEN
        RAISE NOTICE 'La FK original ya está restaurada'; RETURN;
    END IF;
    IF actual.conname<>respaldo.nombre_nuevo OR actual.confrelid<>'public.usuario'::regclass
       OR actual.conkey<>ARRAY[columna]::smallint[] THEN
        RAISE EXCEPTION 'La FK actual no es la instalada por esta reparación';
    END IF;
    IF EXISTS (SELECT 1 FROM public.django_admin_log l
               LEFT JOIN public.auth_user u ON u.id=l.user_id WHERE u.id IS NULL) THEN
        RAISE EXCEPTION 'Hay actores nuevos que no existen en auth_user; reversión cancelada sin cambiar datos';
    END IF;
    IF EXISTS (SELECT 1 FROM public.django_admin_log) AND
       current_setting('vidasys.identidades_verificadas')<>'true' THEN
        RAISE EXCEPTION 'La reversión también requiere verificar identidades; no basta con IDs coincidentes';
    END IF;
    EXECUTE format('ALTER TABLE public.django_admin_log DROP CONSTRAINT %I',actual.conname);
    EXECUTE format('ALTER TABLE public.django_admin_log ADD CONSTRAINT %I %s',
        respaldo.nombre_original,respaldo.definicion_original);
    EXECUTE format('ALTER TABLE public.django_admin_log VALIDATE CONSTRAINT %I',respaldo.nombre_original);
    UPDATE public.vidasys_admin_log_fk_backup SET revertida=true WHERE operacion='admin_log_user_fk_v1';
    RAISE NOTICE 'Definición original restaurada; ninguna fila del historial fue modificada';
END;
$undo$;
COMMIT;
SELECT conname,pg_get_constraintdef(oid),convalidated FROM pg_constraint
WHERE conrelid='public.django_admin_log'::regclass AND contype='f';
