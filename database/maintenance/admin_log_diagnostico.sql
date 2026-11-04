-- Solo lectura; ejecutar en psql con -X -v ON_ERROR_STOP=1.
BEGIN TRANSACTION READ ONLY;
-- Referencias a auth_user en cualquier esquema, y las relaciones principales.
SELECT ns.nspname AS esquema, t.relname AS tabla, c.conname,
       pg_get_constraintdef(c.oid) AS definicion,
       rns.nspname AS esquema_destino, rt.relname AS tabla_destino,
       c.convalidated AS validada
FROM pg_constraint c
JOIN pg_class t ON t.oid=c.conrelid
JOIN pg_namespace ns ON ns.oid=t.relnamespace
JOIN pg_class rt ON rt.oid=c.confrelid
JOIN pg_namespace rns ON rns.oid=rt.relnamespace
WHERE c.contype='f' AND (
    rt.relname='auth_user' OR t.relname IN
    ('django_admin_log','usuario_groups','usuario_user_permissions'))
ORDER BY ns.nspname,t.relname,c.conname;
-- Historial de migraciones, sin modificar ni simular su aplicación.
SELECT app,name,applied FROM public.django_migrations
WHERE app IN ('admin','auth','core') ORDER BY applied,app,name;
-- Solo cantidades, nunca nombres, correos ni contraseñas.
SELECT count(*) AS registros_admin,
       count(*) FILTER (WHERE u.id_usuario IS NULL) AS sin_usuario_personalizado
FROM public.django_admin_log l
LEFT JOIN public.usuario u ON u.id_usuario=l.user_id;
ROLLBACK;
