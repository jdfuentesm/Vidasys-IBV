"""Pruebas de asistencia: ejecutar únicamente con academico.test_settings."""
from datetime import date, time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse

from .models import Asistencia, Calificacion, CicloAcademico, InscripcionCurso, SesionClase
from . import tests as fixtures


class AsistenciaDocenteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.CalificacionesTests.setUpTestData()
        cls.docente = fixtures.CalificacionesTests.docente
        cls.alumno = fixtures.CalificacionesTests.estudiante_usuario
        cls.curso = fixtures.CalificacionesTests.cursos[0]
        cls.ajeno = fixtures.CalificacionesTests.cursos[1]
        cls.inscripcion = fixtures.CalificacionesTests.inscripciones[0]
        cls.otra_materia = fixtures.CalificacionesTests.inscripciones[1]
        cls.segunda = fixtures.CalificacionesTests().agregar_inscripcion()
        cls.sesion = SesionClase.objects.create(curso=cls.curso, numero_clase=1,
            fecha=date(2026, 2, 1), hora_inicio=time(8), hora_fin=time(9), estado='PROGRAMADA')
        cls.sesion2 = SesionClase.objects.create(curso=cls.curso, numero_clase=2,
            fecha=date(2026, 2, 8), hora_inicio=time(8), hora_fin=time(9), estado='IMPARTIDA')
        cls.sesion_ajena = SesionClase.objects.create(curso=cls.ajeno, numero_clase=1,
            fecha=date(2026, 2, 1), hora_inicio=time(8), hora_fin=time(9), estado='PROGRAMADA')

    def setUp(self):
        self.client.force_login(self.docente)
        self.url = reverse('registrar_asistencia')

    def datos(self, sesion=None, estado='PRESENTE'):
        sesion = sesion or self.sesion
        respuesta = self.client.get(self.url, {'curso': self.curso.pk, 'sesion': sesion.pk})
        self.assertEqual(respuesta.status_code, 200)
        datos = {'curso': str(self.curso.pk), 'sesion': str(sesion.pk), 'inscripciones': []}
        for fila in respuesta.context['filas']:
            pk = fila['inscripcion'].pk
            datos['inscripciones'].append(str(pk))
            datos[f'asistencia-{pk}-revision'] = fila['form'].initial['revision']
            if not fila['form'].motivo_bloqueo:
                datos[f'asistencia-{pk}-estado_asistencia'] = estado
                datos[f'asistencia-{pk}-observaciones'] = ''
        return datos

    def registro(self, sesion=None, estado='AUSENTE_INJUSTIFICADA', inscripcion=None):
        return Asistencia.objects.create(inscripcion=inscripcion or self.inscripcion,
            sesion=sesion or self.sesion, estado_asistencia=estado)

    def test_ruta_preservada_y_solo_cursos_docentes(self):
        self.assertEqual(self.url, '/asistencia/')
        respuesta = self.client.get(self.url)
        self.assertEqual([c.pk for c in respuesta.context['cursos']], [self.curso.pk])
        self.assertEqual(self.client.get(self.url, {'curso': self.ajeno.pk}).status_code, 404)

    def test_anonimo_alumno_y_cuenta_inactiva_rechazados(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.alumno)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.docente.estado_cuenta = 'BLOQUEADA'
        self.docente.save(update_fields=['estado_cuenta'])
        self.client.force_login(self.docente)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertFalse(Asistencia.objects.exists())

    def test_sesion_de_otro_curso_rechazada(self):
        self.assertEqual(self.client.get(self.url, {'curso': self.curso.pk, 'sesion': self.sesion_ajena.pk}).status_code, 404)

    def test_masivo_programada_e_impartida_sin_crear_sesiones(self):
        antes = list(SesionClase.objects.order_by('pk').values())
        for sesion in (self.sesion, self.sesion2):
            respuesta = self.client.post(self.url, self.datos(sesion), follow=True)
            self.assertContains(respuesta, 'Asistencia guardada correctamente: 2')
        self.assertEqual(Asistencia.objects.count(), 4)
        self.assertEqual(list(SesionClase.objects.order_by('pk').values()), antes)

    def test_pendientes_no_crean_ausencias(self):
        respuesta = self.client.post(self.url, self.datos(estado=''), follow=True)
        self.assertContains(respuesta, '0 registros guardados')
        self.assertFalse(Asistencia.objects.exists())
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, 'CURSANDO')

    def test_observacion_sin_estado_no_se_guarda(self):
        datos = self.datos(estado='')
        datos[f'asistencia-{self.inscripcion.pk}-observaciones'] = 'Revisar'
        self.assertContains(self.client.post(self.url, datos), 'Seleccione un estado para guardar la observación')
        self.assertFalse(Asistencia.objects.exists())

    def test_diferencia_justificada_e_injustificada(self):
        self.registro(estado='AUSENTE_JUSTIFICADA')
        self.registro(self.sesion2, estado='AUSENTE_INJUSTIFICADA')
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, 'CURSANDO')
        self.assertIsNone(self.inscripcion.fecha_cierre)

    def test_dos_injustificadas_cierran_solo_la_inscripcion(self):
        matricula_antes = self.inscripcion.matricula.__class__.objects.values().get(pk=self.inscripcion.matricula_id)
        otra_antes = InscripcionCurso.objects.values().get(pk=self.otra_materia.pk)
        self.registro()
        datos = self.datos(self.sesion2)
        datos[f'asistencia-{self.inscripcion.pk}-estado_asistencia'] = 'AUSENTE_INJUSTIFICADA'
        respuesta = self.client.post(self.url, datos, follow=True)
        self.assertContains(respuesta, 'REPROBADA_POR_INASISTENCIA')
        self.assertContains(respuesta, 'revisión de Dirección')
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, 'REPROBADA_POR_INASISTENCIA')
        self.assertEqual(self.inscripcion.fecha_cierre, self.sesion2.fecha)
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.otra_materia.pk), otra_antes)
        self.assertEqual(self.inscripcion.matricula.__class__.objects.values().get(pk=self.inscripcion.matricula_id), matricula_antes)
        self.segunda.refresh_from_db()
        self.assertEqual(self.segunda.estado, 'CURSANDO')
        self.assertFalse(Calificacion.objects.exists())

    def test_correccion_ordinaria_actualiza_sin_duplicar(self):
        self.client.post(self.url, self.datos())
        datos = self.datos(estado='AUSENTE_JUSTIFICADA')
        self.assertEqual(self.client.post(self.url, datos).status_code, 302)
        self.assertEqual(Asistencia.objects.count(), 2)
        self.assertEqual(Asistencia.objects.get(inscripcion=self.inscripcion, sesion=self.sesion).estado_asistencia, 'AUSENTE_JUSTIFICADA')

    def test_correccion_de_una_injustificada_reduce_contador_sin_cerrar(self):
        self.registro()
        datos = self.datos(estado='PRESENTE')
        self.client.post(self.url, datos)
        self.assertFalse(Asistencia.objects.filter(inscripcion=self.inscripcion, estado_asistencia='AUSENTE_INJUSTIFICADA').exists())
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, 'CURSANDO')

    def test_cierre_por_inasistencia_no_se_revierte_ni_se_corrige(self):
        self.registro()
        self.registro(self.sesion2)
        antes = InscripcionCurso.objects.values().get(pk=self.inscripcion.pk)
        datos = self.datos()
        datos[f'asistencia-{self.inscripcion.pk}-estado_asistencia'] = 'AUSENTE_JUSTIFICADA'
        respuesta = self.client.post(self.url, datos)
        self.assertContains(respuesta, 'revisión de Dirección')
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.inscripcion.pk), antes)
        self.assertEqual(Asistencia.objects.get(inscripcion=self.inscripcion, sesion=self.sesion).estado_asistencia, 'AUSENTE_INJUSTIFICADA')
        registro = Asistencia.objects.get(inscripcion=self.inscripcion, sesion=self.sesion)
        registro.estado_asistencia = 'PRESENTE'
        with self.assertRaises(ValidationError): registro.save()

    def test_modelo_no_sobrescribe_cierre_de_otro_motivo(self):
        self.registro()
        InscripcionCurso.objects.filter(pk=self.inscripcion.pk).update(fecha_cierre=date(2026,2,3), motivo_cierre='Cierre previo')
        antes = InscripcionCurso.objects.values().get(pk=self.inscripcion.pk)
        with self.assertRaises(ValidationError): self.registro(self.sesion2)
        self.assertEqual(Asistencia.objects.count(), 1)
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.inscripcion.pk), antes)

    def test_matricula_no_activa_excluida_y_historico_solo_lectura(self):
        self.registro(estado='PRESENTE')
        matricula = self.inscripcion.matricula
        matricula.estado = 'ESTADO_NO_HABILITADO'
        matricula.save(update_fields=['estado'])
        respuesta = self.client.get(self.url, {'curso': self.curso.pk, 'sesion': self.sesion.pk})
        fila = next(f for f in respuesta.context['filas'] if f['inscripcion'].pk == self.inscripcion.pk)
        self.assertIn('Matrícula no ACTIVA', fila['form'].motivo_bloqueo)
        respuesta = self.client.get(self.url, {'curso': self.curso.pk, 'sesion': self.sesion2.pk})
        self.assertNotIn(self.inscripcion.pk, [f['inscripcion'].pk for f in respuesta.context['filas']])

    def test_matricula_de_otro_ciclo_no_habilita(self):
        otro = CicloAcademico.objects.create(nombre='II', numero_ciclo=2, anio=2026,
            fecha_inicio=date(2026,1,1), fecha_fin=date(2026,12,31), estado='ACTIVO')
        matricula = self.inscripcion.matricula
        matricula.ciclo = otro
        matricula.save(update_fields=['ciclo'])
        respuesta = self.client.get(self.url, {'curso': self.curso.pk, 'sesion': self.sesion.pk})
        self.assertNotIn(self.inscripcion.pk, [f['inscripcion'].pk for f in respuesta.context['filas']])
        with self.assertRaises(ValidationError): self.registro()

    def test_suspendida_cancelada_solo_consulta(self):
        for estado in ('SUSPENDIDA','CANCELADA'):
            SesionClase.objects.filter(pk=self.sesion.pk).update(estado=estado)
            datos = self.datos()
            respuesta = self.client.get(self.url, {'curso': self.curso.pk, 'sesion': self.sesion.pk})
            self.assertContains(respuesta, 'solo para consulta')
            self.assertEqual(self.client.post(self.url, datos).status_code, 403)
            with self.assertRaises(ValidationError): self.registro()
        self.assertFalse(Asistencia.objects.exists())

    def test_validacion_de_todo_el_lote_conserva_datos(self):
        datos = self.datos()
        datos[f'asistencia-{self.segunda.pk}-estado_asistencia'] = 'ESTADO_INVALIDO'
        respuesta = self.client.post(self.url, datos)
        self.assertContains(respuesta, 'No se guardó ninguna asistencia')
        self.assertTrue(respuesta.context['filas'][1]['form'].errors)
        self.assertFalse(Asistencia.objects.exists())

    def test_fallo_en_segunda_fila_revierte_cierre_y_primera(self):
        self.registro(self.sesion2)
        datos = self.datos(estado='AUSENTE_INJUSTIFICADA')
        original = Asistencia.save
        def guardar(obj, *args, **kwargs):
            if obj.inscripcion_id == self.segunda.pk: raise ValidationError('Fallo simulado')
            return original(obj, *args, **kwargs)
        with patch.object(Asistencia, 'save', guardar):
            self.assertContains(self.client.post(self.url, datos), 'No se guardó ninguna asistencia')
        self.assertEqual(Asistencia.objects.count(), 1)
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, 'CURSANDO')
        self.assertIsNone(self.inscripcion.fecha_cierre)

    def test_identificadores_ajenos_duplicados_o_faltantes_rechazados(self):
        for ids in ([str(self.otra_materia.pk)], [], [str(self.inscripcion.pk)]*2):
            datos = self.datos()
            datos['inscripciones'] = ids
            self.assertEqual(self.client.post(self.url, datos).status_code, 403)
        self.assertFalse(Asistencia.objects.exists())

    def test_revision_obsoleta_no_sobrescribe(self):
        self.registro(estado='PRESENTE')
        datos = self.datos(estado='AUSENTE_JUSTIFICADA')
        registro = Asistencia.objects.get(inscripcion=self.inscripcion, sesion=self.sesion)
        registro.observaciones = 'Modificación concurrente'
        registro.save()
        respuesta = self.client.post(self.url, datos)
        self.assertContains(respuesta, 'habilitación cambió')
        registro.refresh_from_db()
        self.assertEqual(registro.estado_asistencia, 'PRESENTE')
        self.assertEqual(registro.observaciones, 'Modificación concurrente')

    def test_cambio_de_sesion_tras_abrir_rechaza_envio(self):
        datos = self.datos()
        SesionClase.objects.filter(pk=self.sesion.pk).update(estado='CANCELADA')
        self.assertEqual(self.client.post(self.url, datos).status_code, 403)
        self.assertFalse(Asistencia.objects.exists())

    def test_no_se_elimina_registro_al_dejar_estado_vacio(self):
        self.registro(estado='PRESENTE')
        respuesta = self.client.post(self.url, self.datos(estado=''))
        self.assertContains(respuesta, 'Dejarlo vacío no elimina')
        self.assertEqual(Asistencia.objects.count(), 1)

    def test_modelo_rechaza_sesion_ajena_y_duplicados(self):
        with self.assertRaises(ValidationError): self.registro(self.sesion_ajena)
        self.registro()
        with self.assertRaises(ValidationError): self.registro()
        self.assertEqual(Asistencia.objects.count(), 1)

    def test_no_modifica_calificacion_final_ni_cierre_academico(self):
        nota = fixtures.CalificacionesTests().nota()
        nota.save()
        antes_nota = Calificacion.objects.values().get(pk=nota.pk)
        antes_inscripcion = InscripcionCurso.objects.values().get(pk=self.inscripcion.pk)
        with self.assertRaises(ValidationError): self.registro()
        self.assertEqual(Calificacion.objects.values().get(pk=nota.pk), antes_nota)
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.inscripcion.pk), antes_inscripcion)

    def test_csrf_y_error_de_base_sin_detalles(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.docente)
        self.assertEqual(cliente.post(self.url, self.datos()).status_code, 403)
        with patch('academico.views.Curso.objects.filter', side_effect=DatabaseError('detalle privado')):
            respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotContains(respuesta, 'detalle privado', status_code=503)
