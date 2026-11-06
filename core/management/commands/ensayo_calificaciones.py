"""Procedimiento opt-in; por defecto solo inspecciona. Nunca migra el esquema."""
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from academico.forms import FilaCalificacionForm
from academico.models import Calificacion, CicloAcademico, Curso, Estudiante, InscripcionCurso, Maestro, Materia, Matricula
from core.models import Usuario
from core.ensayo_seguro import (
    BASE, EnsayoInseguro, comprobar_configuracion, guardia_sql, inspeccionar, nuevo_id,
    ruta_manifiesto, guardar_manifiesto, leer_manifiesto, permitir_escrituras,
)

MODELOS = {m._meta.label_lower: m for m in
           (Usuario, Maestro, Materia, Curso, Estudiante, Matricula, InscripcionCurso, Calificacion)}


def exigir(condicion, mensaje):
    if not condicion:
        raise EnsayoInseguro(mensaje)


def comprobar_registros(datos, bloquear=False):
    exigir(datos.get("fase") in {"preparado", "probado", "limpio"}, "Manifiesto incompleto; requiere revisión manual.")
    registros = datos.get("registros", [])
    exigir(registros and len({(r["modelo"], r["id"]) for r in registros}) == len(registros), "Lista de registros inválida.")
    for registro in registros:
        modelo = MODELOS.get(registro["modelo"])
        exigir(modelo is not None, "Modelo no autorizado en manifiesto.")
        qs = modelo.objects.filter(pk=registro["id"])
        if bloquear:
            qs = qs.select_for_update()
        objeto = qs.first()
        if datos["fase"] == "limpio":
            exigir(objeto is None, "Un identificador limpiado volvió a utilizarse. No se borrará.")
            continue
        exigir(objeto is not None, "Falta un registro firmado. No se continuará ni limpiará parcialmente.")
        exigir(all(getattr(objeto, campo) == valor for campo, valor in registro["marcas"].items()),
               "Un registro cambió de identidad o relación. Se requiere revisión.")
    return registros


def comprobar_dependencias(datos):
    """Detecta también FK físicas que no figuran en los modelos Django."""
    propios = {}
    for registro in datos["registros"]:
        modelo = MODELOS[registro["modelo"]]
        propios.setdefault(modelo._meta.db_table, {"pk": modelo._meta.pk.column, "ids": []})["ids"].append(registro["id"])
    with connection.cursor() as cursor:
        cursor.execute("""SELECT ns.nspname,c.relname,con.conkey,con.confkey,
             con.confrelid::regclass::text,con.conrelid,
             ARRAY(SELECT attname FROM pg_attribute WHERE attrelid=con.conrelid AND attnum=ANY(con.conkey) ORDER BY attnum),
             ARRAY(SELECT attname FROM pg_attribute WHERE attrelid=con.confrelid AND attnum=ANY(con.confkey) ORDER BY attnum)
             FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
             JOIN pg_namespace ns ON ns.oid=c.relnamespace
             WHERE con.contype='f' AND con.confrelid IN
             (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
              WHERE n.nspname='public' AND c.relname=ANY(%s))""", [list(propios)])
        referencias = cursor.fetchall()
        for esquema, tabla, columnas, destino_cols, destino, oid, nombres, nombres_destino in referencias:
            destino = destino.replace('public.', '').strip('"')
            exigir(destino in propios, "Destino FK inesperado.")
            exigir(len(columnas) == len(destino_cols) == 1 and nombres_destino == [propios[destino]["pk"]],
                   "FK compuesta o sobre clave alternativa: limpieza bloqueada.")
            q = connection.ops.quote_name
            sql = f"SELECT count(*) FROM {q(esquema)}.{q(tabla)} WHERE {q(nombres[0])}=ANY(%s)"
            params = [propios[destino]["ids"]]
            if esquema == "public" and tabla in propios:
                sql += f" AND NOT ({q(propios[tabla]['pk'])}=ANY(%s))"
                params.append(propios[tabla]["ids"])
            cursor.execute(sql, params)
            exigir(cursor.fetchone()[0] == 0, "Existen dependencias ajenas al manifiesto. Limpieza bloqueada.")


def limpiar_registros(datos):
    """Eliminar solo las PK firmadas tras verificar identidad, locks y dependencias."""
    for registro in reversed(datos["registros"]):
        modelo = MODELOS[registro["modelo"]]
        q = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM public.{q(modelo._meta.db_table)} WHERE {q(modelo._meta.pk.column)}=%s", [registro["id"]])
            exigir(cursor.rowcount == 1, "Cantidad inesperada durante limpieza; se revierte todo.")


def guardar_objeto(datos, modelo, marcas, **campos):
    objeto = modelo(**campos, **marcas)
    if isinstance(objeto, Usuario):
        objeto.set_unusable_password()
    objeto.full_clean()
    objeto.save()
    datos["registros"].append({"modelo": modelo._meta.label_lower, "id": objeto.pk, "marcas": marcas})
    return objeto


def preparar(datos, ciclo_id):
    ciclo = CicloAcademico.objects.get(pk=ciclo_id)
    exigir(1 <= ciclo.numero_ciclo <= 4 and ciclo.fecha_inicio <= ciclo.fecha_fin, "Ciclo incompatible.")
    run = datos["run_id"]
    exigir(not Usuario.objects.filter(numero_usuario=run + "-DOC").exists(), "Identificador ya utilizado.")
    usuario = guardar_objeto(datos, Usuario, {"numero_usuario": run + "-DOC", "rol": "MAESTRO"},
        correo_acceso=run.lower() + "@example.invalid", estado_cuenta="ACTIVA",
        is_staff=False, is_superuser=False, debe_cambiar_password=False)
    maestro = guardar_objeto(datos, Maestro, {"usuario_id": usuario.pk, "nombres": "DOCENTE FICTICIO " + run},
        apellidos="SOLO ENSAYO", pais="EL SALVADOR", estado="ACTIVO")
    materia = guardar_objeto(datos, Materia, {"codigo_materia": run + "-MAT"},
        nombre="MATERIA FICTICIA " + run, numero_ciclo_formativo=ciclo.numero_ciclo, estado="ACTIVA")
    curso = guardar_objeto(datos, Curso, {"materia_id": materia.pk, "maestro_id": maestro.pk,
        "ciclo_id": ciclo.pk, "horario": run}, fecha_inicio=ciclo.fecha_inicio,
        fecha_fin=ciclo.fecha_fin, modalidad="PRESENCIAL", estado="ACTIVO")
    datos.update(ciclo_id=ciclo.pk, docente_id=usuario.pk, curso_id=curso.pk, inscripciones=[])
    for i in range(1, 5):
        estudiante = guardar_objeto(datos, Estudiante, {"codigo_estudiante": f"{run}-E{i}"},
            nombres=f"ESTUDIANTE FICTICIO {i}", apellidos=run, fecha_ingreso=ciclo.fecha_inicio, estado="ACTIVO")
        matricula = guardar_objeto(datos, Matricula, {"numero_matricula": f"{run}-M{i}",
            "estudiante_id": estudiante.pk, "ciclo_id": ciclo.pk}, fecha_matricula=ciclo.fecha_inicio,
            estado="ACTIVA", observaciones=run)
        inscripcion = guardar_objeto(datos, InscripcionCurso, {"matricula_id": matricula.pk,
            "curso_id": curso.pk, "observaciones": run}, fecha_inscripcion=ciclo.fecha_inicio, estado="CURSANDO")
        datos["inscripciones"].append(inscripcion.pk)
    datos["fase"] = "preparado"


def payload(datos, *, valores=None):
    perfiles = valores or [
        [40, 20, 20, 20, 0, 75, 75, 75, 75],
        [0] * 9,
        None,
        [40, 20, 20, 20, 0, 60, 60, 60, 65],
    ]
    enviados = {"curso": str(datos["curso_id"]), "inscripciones": [str(i) for i in datos["inscripciones"]]}
    for inscripcion, valores_fila in zip(InscripcionCurso.objects.filter(pk__in=datos["inscripciones"]).order_by("pk"), perfiles):
        nota = Calificacion.objects.filter(inscripcion=inscripcion).first() or Calificacion(inscripcion=inscripcion)
        form = FilaCalificacionForm(inscripcion=inscripcion, instance=nota,
            inscripciones=InscripcionCurso.objects.filter(pk=inscripcion.pk), prefix=f"nota-{inscripcion.pk}")
        enviados[f"nota-{inscripcion.pk}-revision"] = form.initial["revision"]
        for campo, valor in zip(Calificacion.COMPONENTES, valores_fila or [""] * 9):
            enviados[f"nota-{inscripcion.pk}-{campo}"] = str(valor)
        enviados[f"nota-{inscripcion.pk}-observaciones"] = datos["run_id"] if valores_fila is not None else ""
    return enviados


def foto(datos):
    return {
        "notas": list(Calificacion.objects.filter(inscripcion_id__in=datos["inscripciones"]).order_by("pk").values()),
        "inscripciones": list(InscripcionCurso.objects.filter(pk__in=datos["inscripciones"]).order_by("pk").values()),
    }


def verificar(datos):
    notas = {n.inscripcion_id: n for n in Calificacion.objects.filter(inscripcion_id__in=datos["inscripciones"])}
    esperado = [(Decimal("80.00"), "APROBADA"), (Decimal("0.00"), "REPROBADA_ACADEMICAMENTE"), None,
                (Decimal("69.00"), "REPROBADA_ACADEMICAMENTE")]
    for pk, resultado in zip(datos["inscripciones"], esperado):
        inscripcion = InscripcionCurso.objects.get(pk=pk)
        if resultado is None:
            exigir(pk not in notas and inscripcion.estado == "CURSANDO", "La fila pendiente fue alterada.")
        else:
            exigir(pk in notas and (notas[pk].nota_final, notas[pk].estado) == resultado,
                   "Resultado calculado distinto al esperado.")
            exigir(inscripcion.estado == resultado[1] and inscripcion.fecha_cierre is not None,
                   "Cierre académico incorrecto.")
    exigir(len(notas) == 3, "Número de evaluaciones inesperado.")


def probar(datos):
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(Usuario.objects.get(pk=datos["docente_id"]))
    url = reverse("registrar_calificacion")

    def enviar(valores):
        from django.middleware.csrf import get_token
        from django.test import RequestFactory
        request = RequestFactory().get(url)
        token = get_token(request)
        cliente.cookies[settings.CSRF_COOKIE_NAME] = request.META["CSRF_COOKIE"]
        return cliente.post(url, valores, HTTP_X_CSRFTOKEN=token)

    original = foto(datos)
    invalidos = payload(datos)
    invalidos[f"nota-{datos['inscripciones'][3]}-tarea_1"] = "101"
    exigir(enviar(invalidos).status_code == 200 and foto(datos) == original, "Falló la validación atómica.")
    guardar_original = Calificacion.save

    def fallo_controlado(nota, *args, **kwargs):
        if nota.inscripcion_id == datos["inscripciones"][1]:
            raise ValidationError("Fallo controlado del ensayo; debe revertirse todo el lote.")
        return guardar_original(nota, *args, **kwargs)

    with patch.object(Calificacion, "save", fallo_controlado):
        exigir(enviar(payload(datos)).status_code == 200, "No se presentó el fallo controlado.")
    exigir(foto(datos) == original, "El rollback no conservó el estado original.")
    exigir(enviar(payload(datos)).status_code == 302, "No se completó el guardado masivo.")
    verificar(datos)
    antes = foto(datos)
    adulterado = payload(datos)
    adulterado["inscripciones"] = ["0"]
    exigir(enviar(adulterado).status_code == 403 and foto(datos) == antes, "No se rechazó la lista adulterada.")
    ajeno = payload(datos)
    ajeno["curso"] = "0"
    exigir(enviar(ajeno).status_code == 404 and foto(datos) == antes, "No se protegió el curso ajeno/inexistente.")
    anonimo = Client()
    exigir(anonimo.post(url, payload(datos)).status_code == 302, "Acceso anónimo no rechazado.")
    vieja = payload(datos)
    nota = Calificacion.objects.get(inscripcion_id=datos["inscripciones"][0])
    nota.tarea_1 = Decimal("70")
    nota.save()
    actual = foto(datos)
    exigir(enviar(vieja).status_code == 200 and foto(datos) == actual, "Se sobrescribió una revisión obsoleta.")
    exigir(enviar(payload(datos)).status_code == 302, "No se restauró el resultado ficticio esperado.")
    verificar(datos)
    for nota in Calificacion.objects.filter(inscripcion_id__in=datos["inscripciones"]):
        datos["registros"].append({"modelo": "academico.calificacion", "id": nota.pk,
                                  "marcas": {"inscripcion_id": nota.inscripcion_id, "observaciones": datos["run_id"]}})
    datos["fase"] = "probado"
    datos["resultados"] = ["validacion_atomica", "rollback", "masivo", "cero", "pendiente", "permisos", "revision_obsoleta"]


class Command(BaseCommand):
    help = "Ensayo seguro de calificaciones; exige settings_ensayo y una base/rol aislados. No migra."

    def add_arguments(self, parser):
        parser.add_argument("accion", choices=["inspeccionar", "preparar", "probar", "verificar", "limpiar"])
        parser.add_argument("--manifiesto")
        parser.add_argument("--ciclo-id", type=int)
        parser.add_argument("--confirmar", action="store_true")

    def handle(self, *args, **options):
        try:
            comprobar_configuracion(connection)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                huella = inspeccionar(connection)
                exigir(guardia_sql in connection.execute_wrappers, "La guardia SQL no está instalada.")
                exigir(settings.SESSION_ENGINE == "django.contrib.sessions.backends.signed_cookies", "Sesiones de ensayo no aisladas.")
                # Verificar columnas ORM y claves físicas antes de cualquier creación.
                with connection.cursor() as cursor:
                    for modelo in MODELOS.values():
                        columnas = {c.name for c in connection.introspection.get_table_description(cursor, modelo._meta.db_table)}
                        exigir({f.column for f in modelo._meta.local_fields} <= columnas, "Columnas del esquema incompatibles.")
                        constraints = connection.introspection.get_constraints(cursor, modelo._meta.db_table)
                        exigir(any(c.get("primary_key") and c["columns"] == [modelo._meta.pk.column]
                                   for c in constraints.values()), "Clave primaria incompatible.")
                        for campo in modelo._meta.local_fields:
                            if campo.is_relation:
                                destino = campo.remote_field.model
                                exigir(any(c.get("foreign_key") == (destino._meta.db_table, destino._meta.pk.column)
                                           and c["columns"] == [campo.column] for c in constraints.values()),
                                       "Relación física incompatible con el modelo.")
                            if campo.unique and not campo.primary_key:
                                exigir(any((c.get("unique") or c.get("primary_key")) and c["columns"] == [campo.column]
                                           for c in constraints.values()), "Falta una restricción única necesaria.")
            accion = options["accion"]
            if accion == "inspeccionar":
                self.stdout.write("Inspección satisfactoria: base exacta, rol y conexiones aislados; sin escrituras.")
                return
            exigir(options["manifiesto"], "Debe indicar --manifiesto fuera del repositorio.")
            ruta = ruta_manifiesto(options["manifiesto"])
            if accion == "preparar":
                exigir(options["confirmar"] and options["ciclo_id"], "Preparar exige --confirmar y --ciclo-id.")
                datos = {"version": 1, "base": BASE, "huella": huella, "run_id": nuevo_id(), "fase": "preparando", "registros": []}
                guardar_manifiesto(ruta, datos, nuevo=True)
                with permitir_escrituras(), transaction.atomic():
                    preparar(datos, options["ciclo_id"])
                    with connection.cursor() as cursor:
                        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                    guardar_manifiesto(ruta, datos)
                self.stdout.write("Preparado " + datos["run_id"] + ": docente, curso y cuatro inscripciones ficticias.")
                return
            datos = leer_manifiesto(ruta, huella)
            comprobar_registros(datos)
            if accion == "verificar":
                exigir(datos["fase"] == "probado", "Primero debe completar probar.")
                verificar(datos)
                self.stdout.write("Persistencia verificada: 80 aprobada, 0 reprobada, pendiente sin registro, 69 reprobada.")
                return
            if accion == "limpiar" and datos["fase"] == "limpio":
                self.stdout.write("La ejecución ya está limpia. No se modificó nada.")
                return
            if accion == "limpiar" and not options["confirmar"]:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION READ ONLY")
                    comprobar_registros(datos)
                    comprobar_dependencias(datos)
                self.stdout.write(f"Vista previa: se eliminarían {len(datos['registros'])} registros firmados. Ciclo conservado. Use --confirmar solo tras revisar.")
                return
            exigir(options["confirmar"], "Esta acción exige --confirmar.")
            with permitir_escrituras(), transaction.atomic():
                # Bloqueo conservador evita que aparezcan dependencias concurrentes durante la limpieza.
                if accion == "limpiar":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.oid")
                        tablas = cursor.fetchall()
                        # LOCK no está habilitado para otras sentencias: callback seguro explícito tras base verificada.
                        comprobar_configuracion(connection)
                        for esquema, tabla in tablas:
                            q = connection.ops.quote_name
                            with connection.connection.cursor() as raw:
                                raw.execute("SELECT current_database()")
                                exigir(raw.fetchone()[0] == BASE, "Base incorrecta antes de bloquear.")
                                raw.execute(f"LOCK TABLE {q(esquema)}.{q(tabla)} IN SHARE ROW EXCLUSIVE MODE NOWAIT")
                comprobar_registros(datos, bloquear=True)
                if accion == "probar":
                    exigir(datos["fase"] == "preparado", "Probar solo admite una ejecución preparada; no sobrescribe ensayos previos.")
                    probar(datos)
                else:
                    comprobar_dependencias(datos)
                    limpiar_registros(datos)
                    datos["fase"] = "limpio"
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                guardar_manifiesto(ruta, datos)
            if accion == "probar":
                # Conexión nueva fuera de la transacción de escritura: prueba real de persistencia.
                connection.close()
                verificar(datos)
                self.stdout.write("Pruebas completadas y persistencia verificada mediante conexión nueva.")
            else:
                self.stdout.write("Limpieza completada: únicamente claves firmadas del manifiesto; ciclo conservado.")
        except DatabaseError:
            raise CommandError("No se pudo completar/verificar la operación en ensayo. Revise permisos, esquema y manifiesto antes de reintentar; no se mostrará SQL ni información de conexión.") from None
        except (EnsayoInseguro, OSError, ValueError, ValidationError, CicloAcademico.DoesNotExist) as error:
            raise CommandError(str(error)) from error
