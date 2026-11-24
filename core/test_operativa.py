"""F8.3: contratos HTTP y efectos verificables; SQLite en memoria exclusivamente."""
from datetime import date
from decimal import Decimal
import uuid
from unittest.mock import patch
from django.db import DatabaseError, connection
from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from academico import test_flujo as academico_fixture
from academico import test_estudiantes as estudiantes_fixture
from academico.models import Estudiante, Matricula, InscripcionCurso, Curso
from financiero import test_aportes as financiero_fixture
from financiero import test_caja as caja_fixture
from financiero import becas, caja
from financiero.consultas import cuenta, importes, solvente
from financiero.forms import PagoForm
from financiero.models import Pago, Obligacion, MovimientoCaja
from .models import Usuario
from .templatetags.operativa import secciones_operativas


class EstudiantesOperativosF83Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        academico_fixture.FlujoAcademicoTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.secretaria)

    datos = estudiantes_fixture.EstudiantesTests.datos

    def test_inicio_secretaria_sin_informacion_consolidada(self):
        r = self.client.get(reverse('dashboard'))
        for ruta in ('estudiante_nuevo', 'estudiantes', 'matricula_secretaria', 'finanzas_panel', 'caja_listado'):
            self.assertContains(r, reverse(ruta))
        for ruta in ('usuarios', 'finanzas_centro', 'direccion_pendientes'):
            self.assertNotContains(r, f'href="{reverse(ruta)}"')
        self.assertContains(r, 'Otras tareas disponibles')

    def test_formulario_seccionado_conserva_todos_los_campos(self):
        r = self.client.get(reverse('estudiante_nuevo'))
        form = r.context['form']
        grupos = secciones_operativas(form, 'estudiante')
        self.assertEqual({c.name for g in grupos for c in g['campos']}, set(form.fields))
        self.assertContains(r, '<legend>Contacto</legend>', html=True)
        self.assertContains(r, 'inputmode="tel"')
        self.assertContains(r, 'name="csrfmiddlewaretoken"')

    def test_error_conserva_datos_y_enlaces_al_campo(self):
        r = self.client.post(reverse('estudiante_nuevo'), self.datos(fecha_nacimiento='2099-01-01'))
        self.assertContains(r, 'data-errores')
        self.assertContains(r, 'href="#id_fecha_nacimiento"')
        self.assertContains(r, 'value="Ana María"')
        self.assertFalse(Estudiante.objects.filter(codigo_estudiante='NUEVO-001').exists())

    def test_registro_edicion_y_retorno_al_expediente(self):
        r = self.client.post(reverse('estudiante_nuevo'), self.datos())
        e = Estudiante.objects.get(codigo_estudiante='NUEVO-001')
        self.assertRedirects(r, reverse('estudiante_expediente', args=[e.pk]))
        r = self.client.post(reverse('estudiante_editar', args=[e.pk]), self.datos(codigo_estudiante='ALTERADO', nombres='Nombre corregido'))
        self.assertRedirects(r, reverse('estudiante_expediente', args=[e.pk]))
        e.refresh_from_db()
        self.assertEqual(e.codigo_estudiante, 'NUEVO-001')
        self.assertEqual(e.nombres, 'Nombre corregido')

    def test_busqueda_codigo_nombre_y_paginacion_doble(self):
        for n in range(23):
            Estudiante.objects.create(codigo_estudiante=f'F83-{n:02}', nombres=f'Ensayo {n}', apellidos='Ficticio', fecha_ingreso=date(2026,1,1), estado='ACTIVO')
        r = self.client.get(reverse('estudiantes'), {'q': 'F83', 'estado': 'ACTIVO', 'page': 2})
        self.assertEqual(len(r.context['pagina']), 3)
        self.assertContains(r, 'q=F83')
        self.assertContains(r, 'Páginas de estudiantes superior')
        self.assertContains(r, 'Páginas de estudiantes inferior')
        r = self.client.get(reverse('estudiantes'), {'q': 'Ficticio Ensayo 20'})
        self.assertEqual(r.context['pagina'].paginator.count, 1)

    def test_matricula_vista_previa_no_genera_datos(self):
        with CaptureQueriesContext(connection) as consultas:
            r = self.client.get(reverse('estudiante_matricular', args=[self.estudiante.pk]))
        self.assertEqual(len(r.context['vista_ciclos'][0]['cursos']), 6)
        self.assertContains(r, 'No registra un pago')
        self.assertFalse(Matricula.objects.exists())
        self.assertFalse(Obligacion.objects.exists())
        self.assertFalse([q for q in consultas if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))])

    def test_matricula_valida_reintento_y_obligaciones_exactas(self):
        url = reverse('estudiante_matricular', args=[self.estudiante.pk])
        datos = {'estudiante': self.estudiante.pk, 'ciclo': self.ciclo.pk, 'numero_matricula': 'F83-MAT', 'fecha_matricula': '2026-01-02'}
        for _ in range(2):
            r = self.client.post(url, datos)
            self.assertContains(r, 'F83-MAT')
            self.assertContains(r, 'Volver al expediente')
        self.assertEqual(Matricula.objects.count(), 1)
        self.assertEqual(InscripcionCurso.objects.count(), 6)
        self.assertEqual(Obligacion.objects.count(), 6)
        self.assertEqual(sum(Obligacion.objects.values_list('monto_original',flat=True)), Decimal('120'))

    def test_matricula_invalida_preserva_formulario_sin_cambios(self):
        Curso.objects.filter(pk=self.cursos[0].pk).update(estado='CANCELADO')
        r = self.client.post(reverse('estudiante_matricular', args=[self.estudiante.pk]),
            {'ciclo': self.ciclo.pk, 'numero_matricula': 'F83-ERROR', 'fecha_matricula': '2026-01-02'})
        self.assertContains(r, 'value="F83-ERROR"')
        self.assertContains(r, 'data-errores')
        self.assertFalse(Matricula.objects.exists())

    def test_vista_previa_indisponible_no_inventa_cursos(self):
        with patch('academico.presentacion_operativa.ciclos_para_matricula', side_effect=DatabaseError):
            r = self.client.get(reverse('matricula_secretaria'))
        self.assertEqual(r.status_code,200)
        self.assertContains(r, 'No se pudo consultar la vista previa')
        self.assertEqual(r.context['vista_ciclos'], [])

    def test_solvencia_en_expediente_reutiliza_fuente(self):
        r = self.client.get(reverse('estudiante_expediente', args=[self.estudiante.pk]))
        self.assertEqual(r.context['estado_financiero']['solvente'], solvente(self.estudiante))
        self.assertContains(r, 'Ver obligaciones, cobertura y recibos')

    def test_otros_roles_no_acceden_por_url(self):
        for rol in ('MAESTRO', 'ESTUDIANTE', 'PASTOR_PRINCIPAL'):
            u = Usuario.objects.create_user(f'f83-{rol}',f'{rol}@example.test','ficticia',rol=rol)
            self.client.force_login(u)
            for ruta in (reverse('estudiante_nuevo'), reverse('estudiante_matricular', args=[self.estudiante.pk]),reverse('estudiante_expediente', args=[self.estudiante.pk])):
                self.assertEqual(self.client.get(ruta).status_code,403)


class CobrosOperativosF83Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        financiero_fixture.AportesTests.setUpTestData.__func__(cls)

    def setUp(self):
        financiero_fixture.AportesTests.setUp(self)
        self.url = reverse('finanzas_pago', args=[self.estudiante.pk])

    crear_donante = financiero_fixture.AportesTests.crear_donante
    solicitar = financiero_fixture.AportesTests.solicitar
    aprobar = financiero_fixture.AportesTests.aprobar
    cerrar = caja_fixture.CajaTests.cerrar
    convenio = caja_fixture.CajaTests.convenio

    def datos(self, obligacion=None, monto='5.00', **cambios):
        form = self.client.get(self.url).context['form']
        o = obligacion or self.mensualidad
        return {'token':form.initial['token'], 'metodo':'EFECTIVO', 'referencia':'F83 ficticio', f'importe_{o.pk}':monto}|cambios

    def test_cobro_conserva_contrato_y_muestra_fuentes(self):
        r = self.client.get(self.url)
        original = PagoForm(filas=cuenta(self.estudiante)['filas'])
        self.assertEqual(set(r.context['form'].fields),set(original.fields))
        self.assertEqual(len(r.context['cobro_filas']),6)
        self.assertEqual(r.context['saldo_cobro'],Decimal('120'))
        self.assertEqual(r.context['caja_cobro'].pk,self.caja.pk)
        self.assertContains(r, 'data-confirmacion-pago')
        self.assertContains(r, 'Sin JavaScript:')
        self.assertContains(r, 'inputmode="decimal"')

    def test_pago_sin_js_y_reenvio_no_duplica(self):
        datos=self.datos()
        r=self.client.post(self.url,datos,follow=True)
        self.assertContains(r,'Pago registrado correctamente')
        self.assertContains(r,'Imprimir recibo')
        self.assertContains(r,'Volver al expediente del estudiante')
        self.assertEqual(importes(self.mensualidad)[2],Decimal('15'))
        self.client.post(self.url,datos,follow=True)
        self.assertEqual(Pago.objects.count(),1)
        self.assertEqual(MovimientoCaja.objects.count(),1)
        self.assertEqual(Pago.objects.get().monto_total,Decimal('5'))

    def test_total_manipulado_no_se_utiliza(self):
        r=self.client.post(self.url,self.datos(total='9999',saldo='0'),follow=True)
        self.assertEqual(r.status_code,200)
        self.assertEqual(Pago.objects.get().monto_total,Decimal('5'))

    def test_excedente_no_crea_pago_y_preserva_importe(self):
        r=self.client.post(self.url,self.datos(monto='21.00'))
        self.assertContains(r,'data-errores')
        self.assertContains(r,'value="21.00"')
        self.assertFalse(Pago.objects.exists())
        self.assertEqual(importes(self.mensualidad)[2],Decimal('20'))

    def test_decimales_invalidos_se_conservan_sin_pago(self):
        for importe in ('-1.00','1.001','abc'):
            r=self.client.post(self.url,self.datos(monto=importe))
            self.assertTrue(r.context['form'].errors)
        self.assertFalse(Pago.objects.exists())

    def test_caja_cerrada_visible_y_cobro_bloqueado(self):
        self.cerrar()
        r=self.client.get(self.url)
        self.assertIsNone(r.context['caja_cobro'])
        self.assertContains(r,'Necesita abrir su caja')
        r=self.client.post(self.url,self.datos())
        self.assertContains(r,'Abra su caja')
        self.assertFalse(Pago.objects.exists())

    def test_matricula_no_admite_abono_parcial(self):
        o=next(o for o in self.obligaciones if not o.concepto.permite_abonos)
        r=self.client.post(self.url,self.datos(obligacion=o,monto='10.00'))
        self.assertContains(r,'no permite abonos')
        self.assertFalse(Pago.objects.exists())

    def test_padrinazgo_precarga_reserva_sin_registrar_dinero(self):
        self.aprobar()
        r=self.client.get(self.url)
        self.assertTrue(all(f['parte']==0 for f in r.context['cobro_filas']))
        self.assertContains(r,'Reservado a padrinazgo')
        r=self.client.post(self.url,self.datos())
        self.assertContains(r,'padrinazgo autorizado')
        self.assertFalse(Pago.objects.exists())

    def test_convenio_muestra_advertencia_y_rechaza_cobro_ordinario(self):
        self.convenio()
        r=self.client.get(self.url)
        self.assertTrue(all(f['en_convenio'] for f in r.context['cobro_filas']))
        self.assertContains(r,'Use el cobro del convenio')
        self.client.post(self.url,self.datos())
        self.assertFalse(Pago.objects.exists())

    def test_beca_parcial_exige_importe_neto_completo(self):
        o=next(o for o in self.obligaciones if not o.concepto.permite_abonos)
        s=becas.solicitar(usuario=self.secretaria,matricula_id=self.matricula.pk,porcentaje='50',conceptos=['MATRICULA'],alcance='AMBAS',justificacion='Ficticio',clave=uuid.uuid4())
        d=dict(usuario=self.directora,solicitud_id=s.pk,porcentaje='50',conceptos=['MATRICULA'],obligaciones=[o.pk],alcance='AMBAS',observaciones='Ficticio')
        _,revision=becas.previsualizar(**d)
        becas.resolver(**d,decision='APROBADA',revision=revision)
        r=self.client.get(self.url)
        f=next(f for f in r.context['cobro_filas'] if f['obligacion'].pk==o.pk)
        self.assertEqual(f['parte'],Decimal('10'))
        self.client.post(self.url,self.datos(obligacion=o,monto='5.00'))
        self.assertFalse(Pago.objects.exists())
        self.client.post(self.url,self.datos(obligacion=o,monto='10.00'))
        self.assertEqual(Pago.objects.get().monto_total,Decimal('10'))

    def test_fallo_movimiento_revierte_pago_y_detalles(self):
        datos=self.datos()
        with patch('financiero.servicios.MovimientoCaja.objects.create',side_effect=DatabaseError):
            r=self.client.post(self.url,datos)
        self.assertContains(r,'data-errores')
        self.assertFalse(Pago.objects.exists())
        self.assertEqual(importes(self.mensualidad)[2],Decimal('20'))

    def test_fallo_lectura_nueva_no_muestra_cobro_parcial(self):
        with patch('financiero.presentacion_operativa.preparar_cobro',side_effect=DatabaseError):
            r=self.client.get(self.url)
        self.assertEqual(r.status_code,503)
        self.assertNotContains(r,'data-pago-form',status_code=503)

    def test_csrf_sigue_obligatorio(self):
        cliente=Client(enforce_csrf_checks=True)
        cliente.force_login(self.secretaria)
        self.assertEqual(cliente.post(self.url,self.datos()).status_code,403)

    def test_direccion_y_roles_sin_permiso_no_pueden_cobrar(self):
        for u in (self.directora,self.docente):
            self.client.force_login(u)
            self.assertEqual(self.client.get(self.url).status_code,403)
            self.assertEqual(self.client.post(self.url,{}).status_code,403)
        self.assertFalse(Pago.objects.exists())

    def test_abono_separa_cuotas_y_obligaciones_sin_perder_campos(self):
        convenio=self.convenio()
        r=self.client.get(reverse('convenios_cobro',args=[convenio.pk]))
        form=r.context['form']
        grupos=secciones_operativas(form,'abono')
        nombres=[f.name for g in grupos for f in g['campos']]
        self.assertEqual(len(nombres),len(set(nombres)))
        self.assertEqual(set(nombres),{f.name for f in form.visible_fields()})
        self.assertContains(r,'Abonos por cuota')
        self.assertContains(r,'Desglose entre obligaciones originales')
        self.assertContains(r,'name="token"',count=1)
        self.assertContains(r,'data-resumen-abono')

    def test_solicitudes_y_caja_preservan_campos_y_clave(self):
        for ruta,tipo in [('becas_nueva','beca'),('operaciones_ingreso_nuevo','operacion'),('operaciones_egreso_nuevo','operacion'),('caja_apertura','operacion')]:
            r=self.client.get(reverse(ruta))
            form=r.context['form']
            grupos=secciones_operativas(form,tipo)
            self.assertEqual({f.name for g in grupos for f in g['campos']},{f.name for f in form.visible_fields()})
            self.assertContains(r,'name="clave"',count=1)
            self.assertContains(r,'name="csrfmiddlewaretoken"',count=1)
            self.assertNotContains(r,'name="decision"')

    def test_identificacion_accesible_del_importe(self):
        r=self.client.get(self.url)
        self.assertContains(r,'aria-label="Importe a cobrar (USD) · MENSUALIDAD')
