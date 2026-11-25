"""F8.5: lectura propia, privacidad, estados y cifras originales; SQLite efímero."""
from datetime import date,timedelta
from unittest.mock import patch
from django.db import DatabaseError,connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from academico.models import InscripcionCurso,Curso,Calificacion
from financiero import test_aportes as aporte_fixture
from financiero.models import RevisionPadrinazgo
from reportes.financiero_consultas import generar
from . import test_portal as fixture
from .models import Usuario
from .portal_presentacion import compromisos_futuros


class PortalPresentacionF85Tests(TestCase):
    @classmethod
    def setUpTestData(cls):fixture.PortalEstudianteTests.setUpTestData.__func__(cls)
    def setUp(self):self.client.force_login(self.usuario)

    def test_inicio_solo_tareas_y_matricula_permitidas(self):
        r=self.client.get(reverse('portal_inicio'))
        self.assertContains(r,'SOLVENTE')
        self.assertContains(r,reverse('portal_academico'))
        self.assertContains(r,'PROPIA-M1')
        self.assertNotContains(r,'AJENA-PRIVADA')
        self.assertNotContains(r,reverse('finanzas_centro'))

    def test_insolvente_sin_matricula_ni_enlace_academico_principal(self):
        with patch('core.portal.solvente',return_value=False):r=self.client.get(reverse('portal_inicio'))
        self.assertContains(r,'Consulta académica restringida')
        self.assertIsNone(r.context['matricula'])
        self.assertNotContains(r,'PROPIA-M1')
        self.assertNotContains(r,'Consultar materias →')
        self.assertContains(r,reverse('portal_cuenta'))

    def test_error_solvencia_no_asume_cero_ni_acceso(self):
        with patch('core.portal.solvente',side_effect=DatabaseError):
            r=self.client.get(reverse('portal_inicio'))
            self.assertIsNone(r.context['habilitado'])
            self.assertContains(r,'No se pudo verificar el acceso académico')
            self.assertEqual(self.client.get(reverse('portal_academico')).status_code,503)
        self.assertNotContains(r,'PROPIA-M1')

    def test_nota_provisional_no_declara_aprobacion(self):
        r=self.client.get(reverse('portal_academico'))
        self.assertContains(r,'Nota provisional')
        self.assertContains(r,'Cursando')
        self.assertContains(r,'todavía no establece aprobación')
        self.assertNotContains(r,'>Aprobada<')
        self.assertNotContains(r,'<form')

    def test_nota_definitiva_y_estado_son_datos_almacenados(self):
        Curso.objects.filter(pk=self.inscripcion.curso_id).update(estado='FINALIZADO')
        InscripcionCurso.objects.filter(pk=self.inscripcion.pk).update(estado='APROBADA')
        r=self.client.get(reverse('portal_academico'))
        self.assertContains(r,'Nota definitiva')
        self.assertContains(r,'Aprobada')

    def test_registros_faltantes_no_se_convierten_en_ceros(self):
        Calificacion.objects.filter(pk=self.nota.pk).delete()
        r=self.client.get(reverse('portal_academico'))
        self.assertContains(r,'Sin calificación registrada')
        self.assertContains(r,'Sin asistencias registradas')

    def test_cuenta_coincide_con_f7_y_no_ofrece_acciones(self):
        r=self.client.get(reverse('portal_cuenta'))
        t=dict(generar('cuentas',{'estudiante':self.estudiante})['totales'])
        self.assertEqual(r.context['saldo_total'],t['Saldo financiero pendiente'])
        self.assertEqual(r.context['cobertura_total'],t['Protección pendiente efectiva'])
        self.assertEqual(r.context['saldo_estudiante_total'],t['A cargo del estudiante, incluido convenio y no vencido'])
        for texto in ('Registrar pago','Solicitar anulación','AJENO-RECIBO-SECRETO','AJENO-PRIVADO'):
            self.assertNotContains(r,texto)

    def test_manipulacion_params_y_otro_estudiante(self):
        params={'estudiante':self.otro.pk,'curso':self.inscripcion.curso_id,'matricula':self.matricula_ajena.pk,'formato':'csv'}
        for nombre in ('portal_inicio','portal_cuenta','portal_academico'):
            r=self.client.get(reverse(nombre),params)
            self.assertEqual(r.status_code,200)
            self.assertNotContains(r,'AJENO-PRIVADO')
        self.assertEqual(self.client.get(reverse('portal_recibo',args=[self.pago_ajeno.pk]),params).status_code,404)
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(reverse('portal_recibo',args=[self.pago.pk])).status_code,404)

    def test_insolvencia_no_se_elude_con_formatos(self):
        with patch('core.portal.solvente',return_value=False):
            for formato in ('csv','imprimir','json'):
                r=self.client.get(reverse('portal_academico'),{'formato':formato,'estudiante':self.otro.pk})
                self.assertEqual(r.status_code,403)
                self.assertNotContains(r,self.inscripcion.curso.materia.nombre,status_code=403)
        for ruta in (reverse('registrar_calificacion'),reverse('registrar_asistencia'),reverse('reportes_consultar',args=['calificaciones']),reverse('finanzas_centro')):
            self.assertEqual(self.client.get(ruta).status_code,403)

    def test_error_cuenta_no_muestra_saldos_inventados(self):
        with patch('core.portal.cuenta',side_effect=DatabaseError):r=self.client.get(reverse('portal_cuenta'))
        self.assertContains(r,'No se pudo consultar su estado de cuenta')
        self.assertNotContains(r,'Saldo financiero total')
        self.assertContains(r,'PROPIO-RECIBO')

    def test_error_historial_no_muestra_datos_parciales(self):
        with patch('core.portal.Matricula.objects.filter',side_effect=DatabaseError):r=self.client.get(reverse('portal_academico'))
        self.assertEqual(r.status_code,503)
        self.assertNotContains(r,self.inscripcion.curso.materia.nombre,status_code=503)

    def test_error_ciclo_inicio_distingue_ausencia_de_indisponibilidad(self):
        with patch('core.portal.Matricula.objects.filter',side_effect=DatabaseError):r=self.client.get(reverse('portal_inicio'))
        self.assertContains(r,'No se pudo consultar su ciclo')
        self.assertNotContains(r,'No tiene matrículas registradas')

    def test_error_detalle_cobertura_no_cambia_permiso_verificado(self):
        with patch('financiero.aportes.detalle_solvencia',side_effect=DatabaseError):r=self.client.get(reverse('portal_inicio'))
        self.assertTrue(r.context['habilitado'])
        self.assertContains(r,'No se pudo consultar el detalle de cobertura')
        self.assertNotContains(r,'SOLVENTE POR PADRINAZGO')

    def test_lecturas_no_escriben_y_no_hay_formularios(self):
        for nombre in ('portal_inicio','portal_academico','portal_cuenta'):
            with CaptureQueriesContext(connection) as qs:r=self.client.get(reverse(nombre))
            self.assertFalse([q for q in qs if q['sql'].lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER'))])
            self.assertNotContains(r,'<form')
            self.assertIn('no-store',r.headers['Cache-Control'])
            self.assertEqual(self.client.post(reverse(nombre),{}).status_code,405)

    def test_recibo_conserva_propiedad_e_impresion(self):
        r=self.client.get(reverse('portal_recibo',args=[self.pago.pk]))
        self.assertContains(r,'PROPIO-RECIBO')
        self.assertContains(r,'Imprimir recibo')
        self.assertNotContains(r,'Solicitar anulación')
        self.assertNotContains(r,reverse('estudiante_expediente',args=[self.estudiante.pk]))


class CoberturaPrivadaF85Tests(TestCase):
    @classmethod
    def setUpTestData(cls):aporte_fixture.AportesTests.setUpTestData.__func__(cls)
    def setUp(self):
        aporte_fixture.AportesTests.setUp(self)
        self.alumno=Usuario.objects.create_user('f85-alumno','f85@example.test','ficticia',rol='ESTUDIANTE')
        self.estudiante.usuario=self.alumno;self.estudiante.save(update_fields=['usuario'])
        self.client.force_login(self.alumno)
    crear_donante=aporte_fixture.AportesTests.crear_donante
    solicitar=aporte_fixture.AportesTests.solicitar
    aprobar=aporte_fixture.AportesTests.aprobar

    def test_cobertura_efectiva_y_privacidad(self):
        self.aprobar()
        r=self.client.get(reverse('portal_cuenta'))
        self.assertEqual(r.context['cobertura_total'],120)
        self.assertEqual(r.context['saldo_estudiante_total'],0)
        self.assertContains(r,'SOLVENTE POR PADRINAZGO')
        for privado in ('Padrino PRIVADO','PRIVADO-777','privado@example.test','DIRECCION-RESERVADA','NOTA-PRIVADA'):
            self.assertNotContains(r,privado)
        self.assertEqual(self.client.get(reverse('portal_academico')).status_code,200)

    def test_futuro_no_es_cobertura_efectiva_ni_dinero(self):
        inicio=timezone.localdate()+timedelta(days=2)
        self.aprobar(self.solicitar(inicio=inicio,limite=inicio+timedelta(days=20)))
        r=self.client.get(reverse('portal_cuenta'))
        self.assertEqual(r.context['cobertura_total'],0)
        self.assertEqual(r.context['saldo_estudiante_total'],120)
        self.assertEqual(len(r.context['compromisos_futuros']),6)
        self.assertContains(r,'Compromisos con inicio futuro')
        self.assertNotContains(r,'SOLVENTE POR PADRINAZGO')
        self.assertEqual(self.client.get(reverse('portal_academico')).status_code,403)
        for d in r.context['compromisos_futuros']:
            self.assertEqual(set(d),{'obligacion','inicio','limite','asignacion_propia'})
        self.assertNotContains(r,'Padrino PRIVADO')

    def test_proyeccion_no_incluye_compromiso_de_otro(self):
        self.aprobar(self.solicitar(inicio=timezone.localdate()+timedelta(days=1)))
        from academico.models import Estudiante
        otro=Estudiante.objects.create(codigo_estudiante='F85-OTRO',nombres='Otro',apellidos='Ficticio',fecha_ingreso=date(2026,1,1),estado='ACTIVO')
        self.assertEqual(compromisos_futuros(otro),[])

    def test_error_futuros_conserva_saldos_canonicos_y_aviso(self):
        with patch('core.portal_presentacion.compromisos_futuros',side_effect=DatabaseError):r=self.client.get(reverse('portal_cuenta'))
        self.assertContains(r,'No se pudo consultar el detalle de compromisos futuros')
        self.assertEqual(r.context['saldo_total'],120)
        self.assertEqual(r.context['compromisos_futuros'],[])
