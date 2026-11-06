"""Aislamiento y manifiestos del ensayo. No importa modelos ni abre conexiones al importar."""
import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.db import connections
from django.db.backends.signals import connection_created

BASE = "gestion_ibv_ensayo"
_escrituras = ContextVar("ensayo_escrituras", default=False)
TABLAS = ("usuario", "maestro", "materia", "curso", "estudiante", "matricula", "inscripcion_curso", "calificacion")


class EnsayoInseguro(RuntimeError):
    pass


def comprobar_configuracion(connection):
    if not getattr(settings, "ENSAYO_ACTIVO", False) or os.environ.get("DB_NAME") != BASE:
        raise EnsayoInseguro("Use settings_ensayo y DB_NAME=gestion_ibv_ensayo.")
    if set(settings.DATABASES) != {"default"} or settings.DATABASE_ROUTERS:
        raise EnsayoInseguro("No se admiten aliases adicionales ni routers.")
    if (connection.alias != "default" or connection.vendor != "postgresql"
            or connection.settings_dict.get("NAME") != BASE
            or settings.DATABASES["default"].get("NAME") != BASE):
        raise EnsayoInseguro("Conexión no autorizada para el ensayo.")


def guardia_sql(execute, sql, params, many, context):
    connection = context["connection"]
    comprobar_configuracion(connection)
    # Este SET únicamente restringe lecturas; debe ser la primera sentencia de la
    # transacción, antes del SELECT de la guardia. La conexión ya se verificó al abrir.
    if sql.strip().upper() == "SET TRANSACTION READ ONLY":
        return execute(sql, params, many, context)
    # Usar el callback interior evita recursión. Comprobar ANTES de cada escritura.
    execute("SELECT pg_catalog.current_database()", None, False, context)
    if context["cursor"].fetchone()[0] != BASE:
        raise EnsayoInseguro("La conexión real no apunta a gestion_ibv_ensayo.")
    sentencia = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
    if sentencia not in {"SELECT", "SHOW", "SET", "SAVEPOINT", "RELEASE", "ROLLBACK", "INSERT", "UPDATE", "DELETE"}:
        raise EnsayoInseguro("Sentencia no permitida: no se admite DDL, COPY, DO ni SQL arbitrario.")
    if sentencia in {"INSERT", "UPDATE", "DELETE"} and not _escrituras.get():
        raise EnsayoInseguro("Escrituras deshabilitadas fuera de la acción autorizada del comando.")
    if sentencia == "SET" and not re.match(r"SET\s+(TRANSACTION\s+READ\s+ONLY|CONSTRAINTS\s+ALL\s+IMMEDIATE)\s*$", sql, re.I):
        raise EnsayoInseguro("SET no permitido.")
    return execute(sql, params, many, context)


def _conexion_creada(sender, connection, **kwargs):
    comprobar_configuracion(connection)
    with connection.connection.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.current_database()")
        if cursor.fetchone()[0] != BASE:
            connection.close()
            raise EnsayoInseguro("Base real incorrecta; conexión cerrada antes de escribir.")
    if guardia_sql not in connection.execute_wrappers:
        connection.execute_wrappers.append(guardia_sql)


def instalar_guardia():
    connection_created.connect(_conexion_creada, dispatch_uid="vidasys-ensayo-guard", weak=False)
    # También cubre conexiones que el proceso ya hubiera abierto.
    for connection in connections.all(initialized_only=True):
        if connection.connection is not None:
            _conexion_creada(None, connection)


@contextmanager
def permitir_escrituras():
    """Solo invocar tras inspección satisfactoria; nunca expone una opción CLI de bypass."""
    token = _escrituras.set(True)
    try:
        yield
    finally:
        _escrituras.reset(token)


def inspeccionar(connection):
    """Inspección de catálogo, con criterio conservador: ante dudas se rechaza el ensayo."""
    comprobar_configuracion(connection)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_setting('server_version_num')::int, current_schema()")
        nombre, version, esquema = cursor.fetchone()
        if nombre != BASE or version // 10000 != 18 or esquema != "pg_catalog":
            raise EnsayoInseguro("Se requiere PostgreSQL 18, base exacta y search_path pg_catalog,public.")
        cursor.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user")
        if any(cursor.fetchone()):
            raise EnsayoInseguro("El ensayo requiere un rol no privilegiado, sin BYPASSRLS ni creación de roles/bases.")
        cursor.execute("SELECT count(*) FROM pg_database WHERE datallowconn AND datname<>%s AND has_database_privilege(current_user,oid,'CONNECT')", [BASE])
        if cursor.fetchone()[0]:
            raise EnsayoInseguro("No se demuestra aislamiento: el rol puede conectar a otras bases. Un DBA debe restringirlo previamente.")
        cursor.execute("SELECT count(*) FROM pg_foreign_server")
        if cursor.fetchone()[0]:
            raise EnsayoInseguro("Hay servidores externos; no se demuestra ausencia de escrituras indirectas.")
        cursor.execute("SELECT count(*) FROM pg_extension WHERE extname<>'plpgsql'")
        if cursor.fetchone()[0]:
            raise EnsayoInseguro("Hay extensiones adicionales; requiere revisión separada de efectos externos.")
        cursor.execute("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s) AND c.relkind='r' AND NOT c.relispartition AND NOT c.relrowsecurity", [list(TABLAS)])
        if {r[0] for r in cursor.fetchall()} != set(TABLAS):
            raise EnsayoInseguro("Faltan tablas ordinarias esperadas, o existen particiones/RLS.")
        cursor.execute("""SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=ANY(%s) AND NOT t.tgisinternal AND t.tgenabled<>'D'""", [list(TABLAS)])
        if cursor.fetchone()[0]:
            raise EnsayoInseguro("Hay disparadores propios activos. No se crearán datos hasta revisar sus efectos.")
        cursor.execute("""SELECT count(*) FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s)""", [list(TABLAS)])
        if cursor.fetchone()[0]:
            raise EnsayoInseguro("Hay reglas de reescritura; ensayo bloqueado.")
        cursor.execute("""SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_type t ON t.oid=a.atttypid
            JOIN pg_namespace tn ON tn.oid=t.typnamespace WHERE n.nspname='public'
            AND c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped AND tn.nspname<>'pg_catalog'""", [list(TABLAS)])
        if cursor.fetchone()[0]:
            raise EnsayoInseguro("Tipos personalizados no contemplados; revisión necesaria.")
        # Funciones propias en CHECK/default/índices pueden tener efectos laterales.
        cursor.execute("""SELECT count(*) FROM pg_depend d JOIN pg_proc p ON p.oid=d.refobjid
            JOIN pg_namespace n ON n.oid=p.pronamespace WHERE d.refclassid='pg_proc'::regclass
            AND n.nspname NOT IN ('pg_catalog','information_schema')""")
        if cursor.fetchone()[0]:
            raise EnsayoInseguro("Dependencias de funciones propias: no se demuestra ausencia de efectos laterales.")
        cursor.execute("""SELECT count(*) FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
            AND c.relname=ANY(%s) AND con.contype='f' AND NOT con.convalidated""", [list(TABLAS)])
        if cursor.fetchone()[0]:
            raise EnsayoInseguro("Hay claves foráneas sin validar; no se puede asegurar integridad.")
        cursor.execute("SELECT oid,inet_server_addr()::text,inet_server_port() FROM pg_database WHERE datname=current_database()")
        huella = hashlib.sha256(json.dumps(cursor.fetchone(), default=str).encode()).hexdigest()
    return huella


def nuevo_id():
    return "EL-" + uuid.uuid4().hex[:16]


def validar_id(run_id):
    if not re.fullmatch(r"EL-[0-9a-f]{16}", run_id or ""):
        raise EnsayoInseguro("Identificador de ejecución inválido.")


def ruta_manifiesto(value):
    ruta = Path(value).expanduser().resolve()
    repositorio = Path(__file__).resolve().parents[1]
    if ruta.is_relative_to(repositorio) or not ruta.parent.is_dir():
        raise EnsayoInseguro("El manifiesto debe estar fuera del repositorio, en una carpeta existente.")
    return ruta


def guardar_manifiesto(ruta, datos, *, nuevo=False):
    validar_id(datos.get("run_id"))
    if datos.get("base") != BASE:
        raise EnsayoInseguro("Base inválida en el manifiesto.")
    texto = signing.dumps(datos, salt="vidasys-ensayo-v1", compress=True)
    if nuevo:
        descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf8") as archivo:
            archivo.write(texto)
            archivo.flush()
            os.fsync(archivo.fileno())
    else:
        temporal = ruta.with_name(ruta.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with open(temporal, "x", encoding="utf8") as archivo:
                os.chmod(temporal, 0o600)
                archivo.write(texto)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, ruta)
        finally:
            temporal.unlink(missing_ok=True)


def leer_manifiesto(ruta, huella):
    try:
        datos = signing.loads(ruta.read_text(encoding="utf8"), salt="vidasys-ensayo-v1")
    except (OSError, signing.BadSignature, ValueError) as error:
        raise EnsayoInseguro("Manifiesto ausente, ilegible o con firma inválida.") from error
    validar_id(datos.get("run_id"))
    if datos.get("base") != BASE or datos.get("huella") != huella or datos.get("version") != 1:
        raise EnsayoInseguro("El manifiesto no corresponde a esta base/servidor o versión.")
    return datos
