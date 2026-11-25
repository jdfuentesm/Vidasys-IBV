"""Riesgo F8.6: continuidad entre apoyos, cobros y cierre/corrección académica.

Fixture independiente de F7.1: seis cursos activos y datos ficticios. Se invocan
los servicios originales; no se modifica la semilla ni se reparan estados.
"""
import uuid
from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from academico.models import Asistencia, Calificacion, InscripcionCurso, SesionClase
from financiero import becas
from financiero import test_aportes as fixture
from financiero.consultas import cuenta, solvente
from financiero.models import MovimientoCaja, Pago
from reportes.financiero_consultas import generar


class ContinuidadInstitucionalF86Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixture.AportesTests.setUpTestData.__func__(cls)

    crear_donante = fixture.AportesTests.crear_donante
    solicitar = fixture.AportesTests.solicitar
    aprobar = fixture.AportesTests.aprobar
    recibir = fixture.AportesTests.recibir

    def test_apoyos_cobro_idempotente_cierre_y_correccion_sin_efecto_financiero(self):
        fixture.AportesTests.setUp(self)
        self.assertEqual(len(self.cursos), 6)
        self.assertTrue(all(c.estado == 'ACTIVO' for c in self.cursos))
        self.assertEqual(cuenta(self.estudiante)['saldo_total'], Decimal('120'))
        matricula = next(o for o in self.obligaciones if not o.concepto.permite_abonos)
        solicitud = becas.solicitar(usuario=self.secretaria, matricula_id=self.matricula.pk,
            porcentaje='50', conceptos=['MATRICULA'], alcance='AMBAS',
            justificacion='Ensayo integral ficticio', clave=uuid.uuid4())
        datos = dict(usuario=self.directora, solicitud_id=solicitud.pk, porcentaje='50',
            conceptos=['MATRICULA'], alcance='AMBAS', obligaciones=[matricula.pk], observaciones='Ensayo')
        _, revision = becas.previsualizar(**datos)
        becas.resolver(**datos, decision='APROBADA', revision=revision)
        padrinazgo = self.aprobar(self.solicitar(asignaciones=[(self.mensualidad.pk, Decimal('10'))]))

        # Cobro institucional sin JavaScript: importe neto de matrícula y parte
        # completa del estudiante. El reenvío debe devolver el mismo recibo.
        url = reverse('finanzas_pago', args=[self.estudiante.pk])
        form = self.client.get(url).context['form']
        pago = {'token': form.initial['token'], 'metodo': 'EFECTIVO', 'referencia': 'F86 ficticio'}
        for obligacion in self.obligaciones:
            pago[f'importe_{obligacion.pk}'] = '10' if obligacion.pk in (matricula.pk, self.mensualidad.pk) else '20'
        respuesta = self.client.post(url, pago, follow=True)
        self.assertContains(respuesta, 'Imprimir recibo')
        recibo = Pago.objects.get()
        self.assertEqual(recibo.monto_total, Decimal('100'))
        self.assertEqual(self.client.post(url, pago, follow=True).status_code, 200)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        self.assertTrue(solvente(self.estudiante))
        self.assertEqual(cuenta(self.estudiante)['saldo_total'], Decimal('10'))
        self.recibir(modalidad='PADRINAZGO', matricula_id=self.matricula.pk,
            solicitud_id=padrinazgo.pk, monto='10', asignaciones=[(self.mensualidad.pk, Decimal('10'))])
        self.assertEqual(cuenta(self.estudiante)['saldo_total'], Decimal('0'))
        antes_finanzas = dict(generar('resultados', {})['totales'])
        self.assertEqual(antes_finanzas['Ingresos vigentes verificados'], Decimal('110'))
        self.assertEqual(antes_finanzas['Egresos desembolsados vigentes'], Decimal('0'))

        # Calendario impartido como fixture; seis registros presentes por alumno.
        curso = self.cursos[0]
        inscripcion = InscripcionCurso.objects.get(curso=curso, matricula=self.matricula)
        for numero in range(1, 7):
            sesion = SesionClase.objects.create(curso=curso, numero_clase=numero,
                fecha=date(2026, 2, numero), hora_inicio=time(8), hora_fin=time(9), estado='IMPARTIDA')
            Asistencia.objects.create(sesion=sesion, inscripcion=inscripcion, estado_asistencia='PRESENTE')
        self.client.force_login(self.docente)
        libro = reverse('registrar_calificacion')
        fila = self.client.get(libro, {'curso': curso.pk}).context['filas'][0]['form']
        componentes = dict(nota_asistencia='40', nota_uniforme='20', nota_participacion='20',
            nota_companerismo='20', puntos_extras='0', tarea_1='75', examen_1='75', tarea_2='75', examen_2='75')
        notas = {'curso': curso.pk, 'inscripciones': [inscripcion.pk],
            f'nota-{inscripcion.pk}-revision': fila.initial['revision']}
        notas.update({f'nota-{inscripcion.pk}-{campo}': valor for campo, valor in componentes.items()})
        self.assertEqual(self.client.post(libro, notas).status_code, 302)
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, 'CURSANDO')
        cierre = reverse('cierre_curso', args=[curso.pk])
        revision = self.client.get(cierre).context['revision']
        self.assertEqual(self.client.post(cierre, {'revision': revision}).status_code, 302)
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, 'APROBADA')
        fecha_cierre = inscripcion.fecha_cierre

        correccion = reverse('solicitar_correccion', args=[inscripcion.pk])
        form = self.client.get(correccion).context['form']
        propuesta = componentes | {campo: '62.49' for campo in ('tarea_1', 'examen_1', 'tarea_2', 'examen_2')}
        propuesta.update(clave=str(form.initial['clave']), revision=form.initial['revision'], motivo='Rectificación ficticia')
        comparacion = self.client.post(correccion, propuesta)
        propuesta.update(accion='enviar', confirmacion=comparacion.context['form']['confirmacion'].value())
        enviada = self.client.post(correccion, propuesta)
        self.assertEqual(enviada.status_code, 302)
        self.client.force_login(self.directora)
        self.assertEqual(self.client.post(enviada.url, {'decision': 'APROBADA', 'motivo': 'Revisada'}).status_code, 302)
        inscripcion.refresh_from_db(); curso.refresh_from_db()
        self.assertEqual(inscripcion.estado, 'REPROBADA_ACADEMICAMENTE')
        self.assertEqual(Calificacion.objects.get(inscripcion=inscripcion).nota_final, Decimal('69.99'))
        self.assertEqual(inscripcion.fecha_cierre, fecha_cierre)
        self.assertEqual(curso.estado, 'FINALIZADO')
        self.assertEqual(Asistencia.objects.filter(inscripcion=inscripcion, estado_asistencia='PRESENTE').count(), 6)
        self.assertEqual(dict(generar('resultados', {})['totales']), antes_finanzas)
        self.assertEqual(Pago.objects.get().pk, recibo.pk)
