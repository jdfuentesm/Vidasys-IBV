from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection
from django.test import TestCase
from django.urls import reverse

from .forms import UsuarioChangeForm, UsuarioCreationForm
from .models import Usuario


class UsuarioAdminTests(TestCase):
    """Usar --settings=academico.test_settings: solo SQLite efímero."""

    @classmethod
    def setUpTestData(cls):
        cls.administrador = Usuario.objects.create_superuser(
            "admin-prueba", "admin@example.test", "Prueba-Admin-983!"
        )
        cls.estudiante = Usuario.objects.create_user(
            "estudiante-prueba", "estudiante@example.test", "Prueba-Alumno-983!"
        )

    def setUp(self):
        self.client.force_login(self.administrador)

    def datos(self, **cambios):
        datos = {
            "numero_usuario": "docente-prueba", "correo_acceso": "docente@example.test",
            "password1": "Prueba-Docente-983!", "password2": "Prueba-Docente-983!",
            "usable_password": "true", "rol": "MAESTRO", "estado_cuenta": "ACTIVA",
            "_save": "Guardar",
        }
        datos.update(cambios)
        return datos

    def test_modelo_y_formularios_personalizados(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "core.Usuario")
        self.assertIs(get_user_model(), Usuario)
        self.assertIs(LogEntry._meta.get_field("user").remote_field.model, Usuario)
        self.assertIs(UsuarioCreationForm._meta.model, Usuario)
        self.assertIs(UsuarioChangeForm._meta.model, Usuario)
        self.assertIs(admin.site._registry[Usuario].add_form, UsuarioCreationForm)
        self.assertFalse(Usuario._meta.managed)

    def test_formulario_creacion_accesible(self):
        respuesta = self.client.get(reverse("admin:core_usuario_add"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'name="numero_usuario"')
        self.assertContains(respuesta, 'name="password1"')
        self.assertNotContains(respuesta, 'name="username"')

    def test_crear_docente_y_registro_de_auditoria(self):
        respuesta = self.client.post(reverse("admin:core_usuario_add"), self.datos())
        self.assertEqual(respuesta.status_code, 302, getattr(respuesta, "context", None))
        docente = Usuario.objects.get(numero_usuario="docente-prueba")
        self.assertTrue(docente.check_password("Prueba-Docente-983!"))
        self.assertNotEqual(docente.password, "Prueba-Docente-983!")
        self.assertEqual(docente.rol, "MAESTRO")
        self.assertFalse(docente.is_superuser)
        registro = LogEntry.objects.get(action_flag=ADDITION, object_id=str(docente.pk))
        self.assertEqual(registro.user_id, self.administrador.pk)
        self.assertEqual(registro.user, self.administrador)
        self.assertEqual(registro.content_type.model, "usuario")
        self.assertNotIn("Prueba-Docente-983!", registro.change_message)
        with connection.cursor() as cursor:
            self.assertNotIn("auth_user", connection.introspection.table_names(cursor))

    def test_claves_distintas_no_crean_usuario_ni_historial(self):
        respuesta = self.client.post(reverse("admin:core_usuario_add"), self.datos(password2="Otra-983!"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["adminform"].form.errors)
        self.assertFalse(Usuario.objects.filter(numero_usuario="docente-prueba").exists())
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_usuario_duplicado_no_crea_historial(self):
        self.client.post(reverse("admin:core_usuario_add"), self.datos())
        respuesta = self.client.post(reverse("admin:core_usuario_add"), self.datos())
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Usuario.objects.filter(numero_usuario="docente-prueba").count(), 1)
        self.assertEqual(LogEntry.objects.count(), 1)

    def test_edicion_conserva_historial_y_registra_actor(self):
        self.client.post(reverse("admin:core_usuario_add"), self.datos())
        docente = Usuario.objects.get(numero_usuario="docente-prueba")
        respuesta = self.client.post(reverse("admin:core_usuario_change", args=[docente.pk]), {
            "numero_usuario": docente.numero_usuario,
            "correo_acceso": "docente-editado@example.test", "rol": "MAESTRO",
            "estado_cuenta": "ACTIVA", "_save": "Guardar",
        })
        self.assertEqual(respuesta.status_code, 302)
        docente.refresh_from_db()
        self.assertEqual(docente.correo_acceso, "docente-editado@example.test")
        self.assertTrue(docente.check_password("Prueba-Docente-983!"))
        self.assertEqual(LogEntry.objects.filter(object_id=str(docente.pk)).count(), 2)
        self.assertEqual(LogEntry.objects.get(action_flag=CHANGE).user_id, self.administrador.pk)

    def test_fallo_de_auditoria_revierte_creacion_sin_desactivarla(self):
        usuario_admin = admin.site._registry[Usuario]
        with patch.object(usuario_admin, "log_addition", side_effect=IntegrityError("FK simulada")):
            with self.assertRaises(IntegrityError):
                self.client.post(reverse("admin:core_usuario_add"), self.datos())
        self.assertFalse(Usuario.objects.filter(numero_usuario="docente-prueba").exists())
        self.assertFalse(LogEntry.objects.exists())
        self.assertTrue(Usuario.objects.filter(pk=self.administrador.pk).exists())

    def test_creacion_rechazada_sin_permisos(self):
        self.client.force_login(self.estudiante)
        respuesta = self.client.post(reverse("admin:core_usuario_add"), self.datos())
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Usuario.objects.filter(numero_usuario="docente-prueba").exists())
        self.assertFalse(LogEntry.objects.exists())

    def test_fk_historial_y_permisos_apuntan_a_usuario(self):
        with connection.cursor() as cursor:
            for tabla, columna in (("django_admin_log", "user_id"),
                                   ("usuario_groups", "usuario_id"),
                                   ("usuario_user_permissions", "usuario_id")):
                constraints = connection.introspection.get_constraints(cursor, tabla)
                targets = [c["foreign_key"] for c in constraints.values()
                           if c.get("foreign_key") and c["columns"] == [columna]]
                self.assertEqual(targets, [("usuario", "id_usuario")])

    def test_diagnostico_compatible_solo_lectura(self):
        salida = StringIO()
        sentencias = []
        def registrar(execute, sql, params, many, context):
            sentencias.append(sql.lstrip().split()[0].upper())
            return execute(sql, params, many, context)
        with connection.execute_wrapper(registrar):
            call_command("auditar_referencias_usuario", stdout=salida)
        self.assertTrue(all(s in ("SELECT", "PRAGMA", "WITH", "SAVEPOINT", "RELEASE") for s in sentencias), set(sentencias))
        self.assertIn("Referencias principales compatibles", salida.getvalue())
        self.assertNotIn("admin@example.test", salida.getvalue())

    def test_diagnostico_detecta_fk_heredada(self):
        original = connection.introspection.get_constraints
        def constraints(cursor, table):
            resultado = original(cursor, table)
            if table == "django_admin_log":
                for valor in resultado.values():
                    if valor.get("foreign_key") and valor["columns"] == ["user_id"]:
                        valor["foreign_key"] = ("auth_user", "id")
            return resultado
        salida = StringIO()
        with patch.object(connection.introspection, "get_constraints", side_effect=constraints):
            with self.assertRaises(CommandError):
                call_command("auditar_referencias_usuario", stdout=salida)
        self.assertIn("HEREDADA: django_admin_log.user_id", salida.getvalue())
