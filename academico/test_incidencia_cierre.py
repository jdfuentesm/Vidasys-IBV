"""Incidencia de etiqueta tras cierre: reproducción sin corregir producción."""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .flujo import matricular, cerrar_curso, firma_cierre, pendientes_asistencia
from .models import Asistencia, Calificacion, Estudiante, InscripcionCurso, SesionClase


class IncidenciaCierreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_flujo import FlujoAcademicoTests
        FlujoAcademicoTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.curso = self.cursos[0]
        segundo = Estudiante.objects.create(codigo_estudiante='INCIDENCIA-E2', nombres='Alumno ficticio',
            apellidos='Segundo', fecha_ingreso=date(2026, 1, 1), estado='ACTIVO')
        self.inscripciones = []
        for alumno, numero, evaluacion in [(self.estudiante, 'INC-1', '82.50'), (segundo, 'INC-2', '87.50')]:
            _, inscripciones, _ = matricular(estudiante=alumno, ciclo=self.ciclo, numero_matricula=numero,
                fecha_matricula=date(2026, 1, 2))
            inscripcion = next(i for i in inscripciones if i.curso_id == self.curso.pk)
            self.inscripciones.append(inscripcion)
            Calificacion.objects.create(inscripcion=inscripcion, nota_asistencia=Decimal('40'),
                nota_uniforme=Decimal('20'), nota_participacion=Decimal('20'), nota_companerismo=Decimal('20'),
                puntos_extras=Decimal('0'), tarea_1=Decimal(evaluacion), examen_1=Decimal(evaluacion),
                tarea_2=Decimal(evaluacion), examen_2=Decimal(evaluacion))
        for n in range(1, 7):
            sesion = SesionClase.objects.create(curso=self.curso, numero_clase=n, fecha=date(2026, 2, n),
                hora_inicio=time(8), hora_fin=time(9), estado='IMPARTIDA')
            for inscripcion in self.inscripciones:
                Asistencia.objects.create(inscripcion=inscripcion, sesion=sesion, estado_asistencia='PRESENTE')
        self.client.force_login(self.docente)

    def cerrar(self):
        sesiones = list(SesionClase.objects.filter(curso=self.curso).order_by('numero_clase'))
        cerrar_curso(self.curso.pk, self.docente, firma_cierre(self.curso, sesiones))

    def test_seis_presentes_86_y_90_cierran_ambas_inscripciones_aprobadas(self):
        self.assertEqual(pendientes_asistencia(self.curso)['cantidad'], 0)
        self.assertEqual(pendientes_asistencia(self.curso)['errores'], [])
        self.cerrar()
        self.curso.refresh_from_db()
        self.assertEqual(self.curso.estado, 'FINALIZADO')
        for inscripcion, resultado in zip(self.inscripciones, ['86.00', '90.00']):
            inscripcion.refresh_from_db()
            nota = Calificacion.objects.get(inscripcion=inscripcion)
            self.assertEqual(inscripcion.estado, 'APROBADA')
            self.assertEqual(nota.estado, 'APROBADA')
            self.assertEqual(nota.nota_final, Decimal(resultado))
            self.assertEqual(Asistencia.objects.filter(inscripcion=inscripcion, estado_asistencia='PRESENTE').count(), 6)
            self.assertEqual(Asistencia.objects.filter(inscripcion=inscripcion, estado_asistencia='AUSENTE_INJUSTIFICADA').count(), 0)
        response = self.client.get(reverse('registrar_calificacion'), {'curso': self.curso.pk})
        for fila in response.context['filas']:
            self.assertTrue(fila['form'].bloqueada)
            self.assertEqual(fila['form'].motivo_bloqueo, 'Curso no activo: notas solo para consulta.')
            self.assertEqual(fila['inscripcion'].estado, 'APROBADA')

    def test_ausencias_en_otro_curso_no_reprobaran_este_curso(self):
        otra = InscripcionCurso.objects.get(matricula=self.inscripciones[0].matricula, curso=self.cursos[1])
        for n in range(1, 3):
            sesion = SesionClase.objects.create(curso=self.cursos[1], numero_clase=n, fecha=date(2026, 2, n),
                hora_inicio=time(10), hora_fin=time(11), estado='IMPARTIDA')
            Asistencia.objects.create(inscripcion=otra, sesion=sesion, estado_asistencia='AUSENTE_INJUSTIFICADA')
        otra.refresh_from_db()
        self.assertEqual(otra.estado, 'REPROBADA_POR_INASISTENCIA')
        self.cerrar()
        for inscripcion in self.inscripciones:
            inscripcion.refresh_from_db()
            self.assertEqual(inscripcion.estado, 'APROBADA')

    def test_no_debe_mostrar_inasistencia_en_aprobadas(self):
        self.cerrar()
        response = self.client.get(reverse('registrar_calificacion'), {'curso': self.curso.pk})
        self.assertNotContains(response, 'Bloqueada por inasistencia')
        self.assertContains(response, 'Aprobada', count=2)

    def test_etiqueta_inasistencia_solo_para_inscripcion_realmente_reprobada(self):
        for registro in Asistencia.objects.filter(inscripcion=self.inscripciones[0]).order_by('pk')[:2]:
            registro.estado_asistencia = 'AUSENTE_INJUSTIFICADA'
            registro.save()
        self.cerrar()
        response = self.client.get(reverse('registrar_calificacion'), {'curso': self.curso.pk})
        self.assertContains(response, 'Bloqueada por inasistencia', count=1)
        self.assertContains(response, '>Aprobada</span>', count=1)

    def test_reprobacion_academica_no_se_presenta_como_inasistencia(self):
        nota = Calificacion.objects.get(inscripcion=self.inscripciones[0])
        for componente in Calificacion.COMPONENTES:
            setattr(nota, componente, Decimal('0'))
        nota.save()
        self.cerrar()
        response = self.client.get(reverse('registrar_calificacion'), {'curso': self.curso.pk})
        self.assertContains(response, 'Reprobada académicamente', count=1)
        self.assertNotContains(response, 'Bloqueada por inasistencia')
        self.assertContains(response, '>Aprobada</span>', count=1)
