-- Solo para el inicializador de una demo vacía, dentro de su transacción.
-- Reproduce restricciones de los parches 19, 21, 22 y 23 sin datos ni DROP.
ALTER TABLE public.materia ADD CONSTRAINT ck_materia_ciclo_formativo
    CHECK (numero_ciclo_formativo BETWEEN 1 AND 4);
ALTER TABLE public.calificacion ADD CONSTRAINT ck_calificacion_estado
    CHECK (estado IN ('PENDIENTE', 'APROBADA', 'REPROBADA_ACADEMICAMENTE'));
ALTER TABLE public.sesion_clase ADD CONSTRAINT ck_sesion_numero_clase
    CHECK (numero_clase BETWEEN 1 AND 8);
ALTER TABLE public.sesion_clase ADD CONSTRAINT ck_sesion_estado
    CHECK (estado IN ('PROGRAMADA', 'IMPARTIDA', 'SUSPENDIDA', 'CANCELADA'));
ALTER TABLE public.sesion_clase ADD CONSTRAINT ck_sesion_extension_autorizada CHECK (
    (numero_clase BETWEEN 1 AND 6 AND es_extraordinaria = FALSE)
    OR (numero_clase BETWEEN 7 AND 8 AND es_extraordinaria = TRUE
        AND id_usuario_autoriza IS NOT NULL AND fecha_autorizacion IS NOT NULL
        AND NULLIF(BTRIM(motivo_extension), '') IS NOT NULL)
);
