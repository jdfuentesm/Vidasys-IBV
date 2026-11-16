"""Controles esenciales del portal: datos ficticios y SQLite efímero."""
from datetime import date, time
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academico import test_flujo as fixtures
from academico.flujo import matricular
from academico.models import Asistencia, Calificacion, Estudiante, InscripcionCurso, Matricula, SesionClase
from core.models import Usuario
from financiero.models import ConvenioPago, ConvenioObligacion, DetallePago, Obligacion, Pago


class PortalEstudianteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.FlujoAcademicoTests.setUpTestData()
        base = fixtures.FlujoAcademicoTests
        cls.usuario = Usuario.objects.create_user('portal-propio', 'propio@example.test', 'ficticia', rol='ESTUDIANTE')
        cls.ajeno = Usuario.objects.create_user('portal-ajeno', 'ajeno@example.test', 'ficticia', rol='ESTUDIANTE')
        cls.secretaria = base.secretaria
        cls.estudiante = base.estudiante
        cls.estudiante.usuario = cls.usuario
        cls.estudiante.save(update_fields=['usuario'])
        cls.otro = Estudiante.objects.create(usuario=cls.ajeno, codigo_estudiante='AJENO-PRIVADO',
            nombres='Persona ajena', apellidos='Reservada', fecha_ingreso=date(2026,1,1), estado='ACTIVO')
        cls.matricula = matricular(estudiante=cls.estudiante,ciclo=base.ciclo,numero_matricula='PROPIA-M1',fecha_matricula=date(2026,1,2))[0]
        cls.matricula_ajena = matricular(estudiante=cls.otro,ciclo=base.ciclo,numero_matricula='AJENA-PRIVADA',fecha_matricula=date(2026,1,2))[0]
        for n,o in enumerate(cls.matricula.obligaciones.order_by('pk'), 1):
            o.fecha_vencimiento=date(2027,n,10)
            o.save(update_fields=['fecha_vencimiento'])
        cls.inscripcion=cls.matricula.inscripciones.order_by('pk').first()
        cls.sesion=SesionClase.objects.create(curso=cls.inscripcion.curso,numero_clase=1,fecha=date(2026,2,1),hora_inicio=time(8),hora_fin=time(9),estado='IMPARTIDA')
        Asistencia.objects.create(inscripcion=cls.inscripcion,sesion=cls.sesion,estado_asistencia='PRESENTE')
        cls.nota=Calificacion.objects.create(inscripcion=cls.inscripcion,**dict(zip(Calificacion.COMPONENTES,[40,20,20,20,0,80,80,80,80])))
        cls.pago=Pago.objects.create(estudiante=cls.estudiante,usuario=base.secretaria,numero_recibo='PROPIO-RECIBO',
            fecha_pago=timezone.now(),monto_total='5.00',metodo_pago='EFECTIVO',estado='REGISTRADO')
        DetallePago.objects.create(pago=cls.pago,obligacion=cls.matricula.obligaciones.order_by('pk').first(),monto_aplicado='5.00')
        cls.pago_ajeno=Pago.objects.create(estudiante=cls.otro,usuario=base.secretaria,numero_recibo='AJENO-RECIBO-SECRETO',
            fecha_pago=timezone.now(),monto_total='5.00',metodo_pago='EFECTIVO',estado='REGISTRADO')

    def login(self):
        self.client.force_login(self.usuario)

    def test_acceso_desde_autenticacion_y_consulta_propia(self):
        self.assertTrue(self.client.login(username='portal-propio',password='ficticia'))
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('portal_inicio'))
        respuesta=self.client.get(reverse('portal_inicio'))
        self.assertContains(respuesta, self.estudiante.nombres)
        self.assertContains(respuesta, 'PROPIA-M1')
        self.assertContains(respuesta, str(self.matricula.ciclo))
        self.assertIn('no-store',respuesta.headers['Cache-Control'])
        respuesta=self.client.get(reverse('portal_academico'))
        self.assertContains(respuesta, self.inscripcion.curso.materia.nombre)
        self.assertContains(respuesta, 'Nota final registrada')
        self.assertContains(respuesta, 'Presente')
        self.assertContains(respuesta, 'Clase 1')
        self.assertNotContains(respuesta, 'AJENA-PRIVADA')
        self.assertEqual(list(respuesta.context['matriculas']),[self.matricula])
        self.assertNotContains(respuesta,'<form')

    def test_parametros_no_cambian_identidad_y_recibo_ajeno_404(self):
        self.login()
        parametros={'estudiante_id':self.otro.pk,'estudiante':self.otro.pk,'usuario':self.ajeno.pk,'matricula':self.matricula_ajena.pk,'pago_id':self.pago_ajeno.pk}
        for nombre in ('portal_inicio','portal_academico','portal_cuenta'):
            respuesta=self.client.get(reverse(nombre),parametros)
            self.assertEqual(respuesta.status_code,200)
            self.assertNotContains(respuesta,'AJENO-PRIVADO')
            self.assertNotContains(respuesta,'AJENA-PRIVADA')
            self.assertNotContains(respuesta,'AJENO-RECIBO-SECRETO')
        self.assertEqual(self.client.get(reverse('portal_recibo',args=[self.pago_ajeno.pk]),parametros).status_code,404)
        respuesta=self.client.get(reverse('portal_recibo',args=[self.pago.pk]),parametros)
        self.assertContains(respuesta,'PROPIO-RECIBO')
        self.assertNotContains(respuesta,'AJENO-RECIBO-SECRETO')

    def test_insolvencia_bloquea_todo_academico_pero_conserva_cuenta_y_recibo(self):
        self.login()
        obligacion=self.matricula.obligaciones.order_by('pk').first()
        obligacion.fecha_vencimiento=date(2026,1,10)
        obligacion.save(update_fields=['fecha_vencimiento'])
        antes=([*Calificacion.objects.values()],[*Asistencia.objects.values()],[*InscripcionCurso.objects.values()],[*Matricula.objects.values()])
        respuesta=self.client.get(reverse('portal_inicio'))
        self.assertContains(respuesta,'Consulta académica restringida')
        self.assertNotContains(respuesta,'PROPIA-M1')
        self.assertIsNone(respuesta.context['matricula'])
        respuesta=self.client.get(reverse('portal_academico'))
        self.assertEqual(respuesta.status_code,403)
        self.assertNotContains(respuesta,self.inscripcion.curso.materia.nombre,status_code=403)
        self.assertNotIn('matriculas',respuesta.context)
        respuesta=self.client.get(reverse('portal_cuenta'))
        self.assertContains(respuesta,'INSOLVENTE')
        self.assertContains(respuesta,'PROPIO-RECIBO')
        self.assertContains(self.client.get(reverse('portal_recibo',args=[self.pago.pk])),'PROPIO-RECIBO')
        despues=([*Calificacion.objects.values()],[*Asistencia.objects.values()],[*InscripcionCurso.objects.values()],[*Matricula.objects.values()])
        self.assertEqual(antes,despues)

    def test_convenio_vigente_conserva_excepcion_y_se_revalida_cada_peticion(self):
        self.login()
        o=self.matricula.obligaciones.order_by('pk').first()
        o.fecha_vencimiento=date(2026,1,10);o.save(update_fields=['fecha_vencimiento'])
        self.assertEqual(self.client.get(reverse('portal_academico')).status_code,403)
        convenio=ConvenioPago.objects.create(estudiante=self.estudiante,usuario_autoriza=self.secretaria,
            fecha_convenio=date(2026,1,1),monto_convenido='15',numero_cuotas=1,estado='ACTIVO')
        ConvenioObligacion.objects.create(convenio=convenio,obligacion=o,saldo_incluido='15')
        self.assertContains(self.client.get(reverse('portal_academico')),'Nota final registrada')
        ConvenioPago.objects.filter(pk=convenio.pk).update(estado='INCUMPLIDO')
        self.assertEqual(self.client.get(reverse('portal_academico')).status_code,403)

    def test_estado_cuenta_reutilizado_solo_propio_sin_acciones_de_pago(self):
        self.login()
        respuesta=self.client.get(reverse('portal_cuenta'))
        self.assertContains(respuesta,'PROPIO-RECIBO')
        self.assertContains(respuesta,'115,00')
        self.assertNotContains(respuesta,'AJENO-RECIBO-SECRETO')
        self.assertNotContains(respuesta,reverse('finanzas_pago',args=[self.estudiante.pk]))
        self.assertNotContains(respuesta,reverse('estudiante_expediente',args=[self.estudiante.pk]))
        self.assertContains(respuesta,reverse('portal_recibo',args=[self.pago.pk]))

    def test_sin_vinculo_sin_rol_o_inactivo_no_accede_y_no_autovincula(self):
        sin=Usuario.objects.create_user('sin-vinculo','sin@example.test','ficticia',rol='ESTUDIANTE')
        self.client.force_login(sin)
        for nombre in ('portal_inicio','portal_academico','portal_cuenta'):
            self.assertContains(self.client.get(reverse(nombre)),'Cuenta sin expediente verificado',status_code=403)
        self.assertFalse(Estudiante.objects.filter(usuario=sin).exists())
        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(reverse('portal_inicio')).status_code,403)
        self.usuario.estado_cuenta='INACTIVA';self.usuario.save(update_fields=['estado_cuenta'])
        self.client.force_login(self.usuario)
        self.assertIn(self.client.get(reverse('portal_cuenta')).status_code,(302,403))
        self.client.logout()
        self.assertEqual(self.client.get(reverse('portal_inicio')).status_code,302)

    def test_no_escrituras_ni_endpoints_alternativos(self):
        self.login()
        for nombre,args in [('portal_inicio',[]),('portal_academico',[]),('portal_cuenta',[]),('portal_recibo',[self.pago.pk])]:
            self.assertEqual(self.client.post(reverse(nombre,args=args),{'estudiante':self.otro.pk}).status_code,405)
        for nombre,args in [('estudiantes',[]),('estudiante_expediente',[self.estudiante.pk]),
                ('registrar_calificacion',[]),('registrar_asistencia',[]),('mis_cursos',[]),
                ('finanzas_panel',[]),('finanzas_cuenta',[self.estudiante.pk]),('finanzas_recibo',[self.pago.pk]),
                ('finanzas_pago',[self.estudiante.pk]),('probar_conexion',[])]:
            self.assertEqual(self.client.get(reverse(nombre,args=args)).status_code,403)

    def test_error_de_solvencia_no_abre_consulta_academica(self):
        self.login()
        with patch('core.portal.solvente',side_effect=DatabaseError('Fallo ficticio')):
            respuesta=self.client.get(reverse('portal_inicio'))
            self.assertContains(respuesta,'No se pudo verificar el acceso académico')
            self.assertNotContains(respuesta,'PROPIA-M1')
            self.assertEqual(self.client.get(reverse('portal_academico')).status_code,503)
