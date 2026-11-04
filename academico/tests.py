from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import resolve, reverse

from core.models import Usuario
from .forms import CalificacionForm
from .models import (
    Calificacion, CicloAcademico, Curso, Estudiante, InscripcionCurso,
    Maestro, Materia, Matricula,
)


class CalificacionesTests(TestCase):
    """Ejecutar con --settings=academico.test_settings (SQLite aislado)."""

    @classmethod
    def setUpTestData(cls):
        cls.docente = Usuario.objects.create_user("docente", "docente@example.test", "clave", rol="MAESTRO")
        cls.otro = Usuario.objects.create_user("otro", "otro@example.test", "clave", rol="MAESTRO")
        cls.estudiante_usuario = Usuario.objects.create_user("alumno", "alumno@example.test", "clave")
        ciclo = CicloAcademico.objects.create(nombre="I", numero_ciclo=1, anio=2026,
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), estado="ACTIVO")
        estudiante = Estudiante.objects.create(codigo_estudiante="E1", nombres="Estudiante", apellidos="Prueba",
            fecha_ingreso=date(2026, 1, 1), estado="ACTIVO", usuario=cls.estudiante_usuario)
        matricula = Matricula.objects.create(estudiante=estudiante, ciclo=ciclo, numero_matricula="M1",
            fecha_matricula=date(2026, 1, 1), estado="ACTIVA")
        cls.cursos = []
        cls.inscripciones = []
        for index, usuario in enumerate((cls.docente, cls.otro)):
            maestro = Maestro.objects.create(usuario=usuario, nombres=f"Docente {index}", apellidos="Prueba", pais="SV", estado="ACTIVO")
            materia = Materia.objects.create(codigo_materia=f"MAT{index}", nombre=f"Materia {index}", numero_ciclo_formativo=1, estado="ACTIVA")
            curso = Curso.objects.create(maestro=maestro, materia=materia, ciclo=ciclo,
                fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), modalidad="PRESENCIAL", estado="ACTIVO")
            cls.cursos.append(curso)
            cls.inscripciones.append(InscripcionCurso.objects.create(matricula=matricula, curso=curso,
                fecha_inscripcion=date(2026, 1, 1), estado="CURSANDO"))

    def datos(self, **cambios):
        datos = dict(curso=str(self.cursos[0].pk), inscripcion=str(self.inscripciones[0].pk),
            nota_asistencia="40", nota_uniforme="20", nota_participacion="20", nota_companerismo="20",
            puntos_extras="10", tarea_1="75", examen_1="75", tarea_2="75", examen_2="75", observaciones="Prueba")
        datos.update(cambios)
        return datos

    def nota(self, **cambios):
        datos = self.datos(**cambios)
        return Calificacion(inscripcion=self.inscripciones[0], **{
            campo: Decimal(datos[campo]) for campo in Calificacion.COMPONENTES
        })

    def test_persistencia_formula_aprobacion_y_cierre(self):
        nota = self.nota()
        nota.save()
        nota.refresh_from_db()
        self.assertEqual(nota.nota_final, Decimal("80.00"))
        self.assertEqual(nota.estado, "APROBADA")
        self.assertIsNotNone(nota.fecha_registro)
        self.inscripciones[0].refresh_from_db()
        self.assertEqual(self.inscripciones[0].estado, "APROBADA")
        self.assertIsNotNone(self.inscripciones[0].fecha_cierre)

    def test_frontera_setenta(self):
        nota = self.nota(tarea_1="50", examen_1="50", tarea_2="50", examen_2="100")
        nota.save()
        self.assertEqual(nota.nota_final, Decimal("70.00"))
        self.assertEqual(nota.estado, "APROBADA")
        nota.examen_2 = Decimal("99.90")
        nota.save()
        nota.refresh_from_db()
        self.assertEqual(nota.nota_final, Decimal("69.98"))
        self.assertEqual(nota.estado, "REPROBADA_ACADEMICAMENTE")

    def test_modificacion_sin_duplicado_y_fecha_original(self):
        nota = self.nota()
        nota.save()
        fecha = nota.fecha_registro
        nota.tarea_1 = Decimal("25")
        nota.save(update_fields=["tarea_1"])
        nota.refresh_from_db()
        self.assertEqual(nota.nota_final, Decimal("70"))
        self.assertEqual(nota.fecha_registro, fecha)
        self.assertEqual(Calificacion.objects.count(), 1)

    def test_evaluacion_en_cero_reprueba(self):
        nota = self.nota()
        nota.save()
        for campo in Calificacion.COMPONENTES:
            setattr(nota, campo, Decimal("0"))
        nota.save()
        nota.refresh_from_db()
        self.assertEqual(nota.nota_final, Decimal("0.00"))
        self.assertEqual(nota.estado, "REPROBADA_ACADEMICAMENTE")
        self.inscripciones[0].refresh_from_db()
        self.assertEqual(self.inscripciones[0].estado, "REPROBADA_ACADEMICAMENTE")
        self.assertIsNotNone(self.inscripciones[0].fecha_cierre)

    def test_limites_servidor(self):
        for campo, limite in Calificacion.LIMITES_COMPONENTES.items():
            with self.subTest(campo=campo):
                with self.assertRaises(ValidationError):
                    self.nota(**{campo: str(limite + 1)}).save()
        for campo in Calificacion.COMPONENTES:
            with self.subTest(negativo=campo):
                with self.assertRaises(ValidationError):
                    self.nota(**{campo: "-1"}).save()
        self.assertEqual(Calificacion.objects.count(), 0)

    def test_rechaza_no_finito_y_precision_excesiva(self):
        for valor in ("NaN", "Infinity", "1.234"):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                self.nota(tarea_1=valor).save()

    def test_bloqueo_inasistencia_modelo_y_formulario(self):
        InscripcionCurso.objects.filter(pk=self.inscripciones[0].pk).update(estado="REPROBADA_POR_INASISTENCIA")
        self.inscripciones[0].refresh_from_db()
        with self.assertRaises(ValidationError):
            self.nota().save()
        form = CalificacionForm(data=self.datos(), inscripciones=InscripcionCurso.objects.all())
        self.assertFalse(form.is_valid())
        self.assertIn("inasistencia", str(form.non_field_errors()))

    def test_formulario_no_expone_inscripciones_por_defecto(self):
        self.assertFalse(CalificacionForm().fields["inscripcion"].queryset.exists())

    def test_anonimo_redirigido(self):
        respuesta = self.client.get(reverse("registrar_calificacion"))
        self.assertRedirects(respuesta, "/login/?next=/calificacion/", fetch_redirect_response=False)

    def test_rol_estudiante_rechazado_get_y_post(self):
        self.client.force_login(self.estudiante_usuario)
        self.assertEqual(self.client.get(reverse("registrar_calificacion")).status_code, 403)
        self.assertEqual(self.client.post(reverse("registrar_calificacion"), self.datos()).status_code, 403)
        self.assertFalse(Calificacion.objects.exists())

    def test_solo_cursos_propios(self):
        self.client.force_login(self.docente)
        respuesta = self.client.get(reverse("registrar_calificacion"))
        self.assertEqual(list(respuesta.context["cursos"]), [self.cursos[0]])
        self.assertEqual(self.client.get(reverse("registrar_calificacion"), {"curso": self.cursos[1].pk}).status_code, 404)

    def test_post_ajeno_y_estudiante_de_otro_curso_rechazados(self):
        self.client.force_login(self.docente)
        for datos in (self.datos(curso=str(self.cursos[1].pk), inscripcion=str(self.inscripciones[1].pk)),
                      self.datos(inscripcion=str(self.inscripciones[1].pk))):
            self.assertEqual(self.client.post(reverse("registrar_calificacion"), datos).status_code, 404)
        self.assertFalse(Calificacion.objects.exists())

    def test_flujo_crear_consultar_modificar(self):
        self.client.force_login(self.docente)
        respuesta = self.client.post(reverse("registrar_calificacion"), self.datos(), follow=True)
        self.assertContains(respuesta, "Calificación registrada correctamente")
        self.assertEqual(respuesta.context["form"].instance.nota_final, Decimal("80"))
        respuesta = self.client.post(reverse("registrar_calificacion"), self.datos(tarea_1="25"), follow=True)
        self.assertContains(respuesta, "Calificación actualizada correctamente")
        self.assertEqual(respuesta.context["form"].initial["tarea_1"], Decimal("25"))
        self.assertEqual(Calificacion.objects.count(), 1)
        self.assertEqual(Calificacion.objects.get().nota_final, Decimal("70"))

    def test_errores_visibles_y_datos_conservados(self):
        self.client.force_login(self.docente)
        respuesta = self.client.post(reverse("registrar_calificacion"), self.datos(nota_asistencia="41"))
        self.assertContains(respuesta, "La nota no puede superar 40")
        self.assertTrue(respuesta.context["form"].is_bound)
        self.assertFalse(Calificacion.objects.exists())

    def test_docente_sin_perfil_no_ve_cursos(self):
        usuario = Usuario.objects.create_user("sinperfil", "sinperfil@example.test", "clave", rol="MAESTRO")
        self.client.force_login(usuario)
        self.assertContains(self.client.get(reverse("registrar_calificacion")), "No hay cursos asignados")

    def test_error_base_sin_detalles_sensibles(self):
        self.client.force_login(self.docente)
        with patch("academico.views.Curso.objects.filter", side_effect=DatabaseError("detalle privado")):
            respuesta = self.client.get(reverse("registrar_calificacion"))
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotContains(respuesta, "detalle privado", status_code=503)
        self.assertContains(respuesta, "estructura de la base", status_code=503)

    def test_tareas_y_examenes_entre_cero_y_cien(self):
        for campo in ("tarea_1", "examen_1", "tarea_2", "examen_2"):
            with self.subTest(campo=campo):
                form = CalificacionForm(data=self.datos(**{campo: "100.01"}),
                    inscripciones=InscripcionCurso.objects.all())
                self.assertFalse(form.is_valid())
                self.assertIn(campo, form.errors)

    def test_extras_solo_cubren_apreciacion_faltante(self):
        nota = self.nota(nota_asistencia="35", puntos_extras="10")
        self.assertEqual(nota.calcular_nota(), Decimal("80"))
        nota.puntos_extras = Decimal("0")
        self.assertEqual(nota.calcular_nota(), Decimal("79"))

    def test_extras_en_blanco_opcionales(self):
        self.client.force_login(self.docente)
        respuesta = self.client.post(reverse("registrar_calificacion"), self.datos(puntos_extras=""))
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Calificacion.objects.get().puntos_extras, Decimal("0"))

    def test_cuenta_inactiva_no_puede_guardar(self):
        self.docente.estado_cuenta = "BLOQUEADA"
        self.docente.save(update_fields=["estado_cuenta"])
        self.client.force_login(self.docente)
        respuesta = self.client.post(reverse("registrar_calificacion"), self.datos())
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Calificacion.objects.exists())

    def test_guardado_atomico_si_falla_cierre(self):
        with patch("django.db.models.query.QuerySet.update", side_effect=DatabaseError("error simulado")):
            with self.assertRaises(DatabaseError):
                self.nota().save()
        self.assertFalse(Calificacion.objects.exists())
        self.inscripciones[0].refresh_from_db()
        self.assertEqual(self.inscripciones[0].estado, "CURSANDO")

    def test_csrf_obligatorio(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.docente)
        self.assertEqual(cliente.post(reverse("registrar_calificacion"), self.datos()).status_code, 403)
        self.assertFalse(Calificacion.objects.exists())

    def test_post_sin_seleccion_muestra_error(self):
        self.client.force_login(self.docente)
        respuesta = self.client.post(reverse("registrar_calificacion"), self.datos(inscripcion=""))
        self.assertContains(respuesta, "Seleccione un estudiante antes de guardar")
        self.assertFalse(Calificacion.objects.exists())

    def test_rutas_preservadas(self):
        for nombre, ruta in (("login", "/login/"), ("logout", "/logout/"), ("dashboard", "/"),
                             ("registrar_asistencia", "/asistencia/"),
                             ("autorizar_clase_extraordinaria", "/autorizar-clase/"),
                             ("registrar_calificacion", "/calificacion/"), ("probar_conexion", "/probar-conexion/")):
            with self.subTest(nombre=nombre):
                self.assertEqual(reverse(nombre), ruta)
                self.assertEqual(resolve(ruta).url_name, nombre)
