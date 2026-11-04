-- NO ejecutar sin respaldo y revisión de identidades históricas.
-- psql -X -v ON_ERROR_STOP=1 -v identidades_verificadas=false -f admin_log_aplicar.sql ...
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
LOCK TABLE public.usuario IN SHARE MODE;
-- Respaldo exclusivamente de metadatos DDL, sin copiar información personal.
CREATE TABLE IF NOT EXISTS public.vidasys_admin_log_fk_backup (
    operacion text PRIMARY KEY,
    nombre_original text NOT NULL,
    definicion_original text NOT NULL,
    nombre_nuevo text NOT NULL,
    revertida boolean NOT NULL DEFAULT false
);
DO $repair$
DECLARE
    actual record;
    respaldo record;
    columna smallint;
    destino smallint;
    total integer;
BEGIN
    SELECT attnum INTO STRICT columna FROM pg_attribute
    WHERE attrelid='public.django_admin_log'::regclass AND attname='user_id' AND NOT attisdropped;
    SELECT attnum INTO STRICT destino FROM pg_attribute
    WHERE attrelid='public.usuario'::regclass AND attname='id_usuario' AND NOT attisdropped;
    SELECT count(*) INTO total FROM pg_constraint
    WHERE conrelid='public.django_admin_log'::regclass AND contype='f' AND columna=ANY(conkey);
    IF total<>1 THEN
        RAISE EXCEPTION 'Se requiere exactamente una FK sobre user_id; encontradas: %',total;
    END IF;
    SELECT * INTO STRICT actual FROM pg_constraint
    WHERE conrelid='public.django_admin_log'::regclass AND contype='f' AND columna=ANY(conkey);
    IF NOT actual.convalidated THEN
        RAISE EXCEPTION 'La FK original no está validada; revisar el esquema antes de reemplazarla';
    END IF;
    IF actual.conkey<>ARRAY[columna]::smallint[] THEN
        RAISE EXCEPTION 'FK compuesta inesperada; requiere diagnóstico manual';
    END IF;
    IF actual.confrelid='public.usuario'::regclass AND actual.confkey=ARRAY[destino]::smallint[] THEN
        EXECUTE format('ALTER TABLE public.django_admin_log VALIDATE CONSTRAINT %I',actual.conname);
        RAISE NOTICE 'La FK ya apunta a usuario.id_usuario; no se reemplaza';
        RETURN;
    END IF;
    IF actual.confrelid IS DISTINCT FROM to_regclass('public.auth_user') OR
       actual.confkey IS DISTINCT FROM ARRAY[(SELECT attnum FROM pg_attribute
         WHERE attrelid=to_regclass('public.auth_user') AND attname='id' AND NOT attisdropped)]::smallint[] THEN
        RAISE EXCEPTION 'Destino inesperado; solo se admite auth_user(id) como origen';
    END IF;
    IF EXISTS (SELECT 1 FROM public.django_admin_log l
               LEFT JOIN public.usuario u ON u.id_usuario=l.user_id WHERE u.id_usuario IS NULL) THEN
        RAISE EXCEPTION 'Hay actores históricos sin usuario correspondiente. Se cancela sin cambiar registros';
    END IF;
    IF EXISTS (SELECT 1 FROM public.django_admin_log) AND
       current_setting('vidasys.identidades_verificadas')<>'true' THEN
        RAISE EXCEPTION 'Debe verificarse la identidad de TODOS los actores históricos; igual ID no prueba igual persona';
    END IF;
    INSERT INTO public.vidasys_admin_log_fk_backup
        (operacion,nombre_original,definicion_original,nombre_nuevo)
    VALUES ('admin_log_user_fk_v1',actual.conname,pg_get_constraintdef(actual.oid),
            'vidasys_admin_log_user_usuario_fk')
    ON CONFLICT (operacion) DO NOTHING;
    SELECT * INTO STRICT respaldo FROM public.vidasys_admin_log_fk_backup
    WHERE operacion='admin_log_user_fk_v1';
    IF respaldo.nombre_original<>actual.conname OR respaldo.definicion_original<>pg_get_constraintdef(actual.oid) THEN
        RAISE EXCEPTION 'El respaldo existente no coincide con la FK actual';
    END IF;
    EXECUTE format('ALTER TABLE public.django_admin_log DROP CONSTRAINT %I',actual.conname);
    ALTER TABLE public.django_admin_log
        ADD CONSTRAINT vidasys_admin_log_user_usuario_fk FOREIGN KEY (user_id)
        REFERENCES public.usuario(id_usuario) DEFERRABLE INITIALLY DEFERRED NOT VALID;
    ALTER TABLE public.django_admin_log VALIDATE CONSTRAINT vidasys_admin_log_user_usuario_fk;
    UPDATE public.vidasys_admin_log_fk_backup SET revertida=false WHERE operacion='admin_log_user_fk_v1';
    RAISE NOTICE 'FK corregida y validada. No se modificaron filas de usuarios ni del historial';
END;
$repair$;
COMMIT;
-- Comprobación posterior: la relación debe mostrar usuario(id_usuario), validada.
SELECT conname,pg_get_constraintdef(oid),convalidated FROM pg_constraint
WHERE conrelid='public.django_admin_log'::regclass AND conname='vidasys_admin_log_user_usuario_fk';
