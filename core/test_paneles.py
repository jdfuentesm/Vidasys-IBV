"""F8.2: fuentes verificables, consulta sin escritura y permisos originales."""
from datetime import timedelta,date,time
from decimal import Decimal
import uuid
from unittest.mock import patch
from django.db import connection,DatabaseError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from core.models import Usuario
from academico.models import Estudiante,SesionClase,SolicitudAcademica
from academico import solicitudes as academicas
from financiero import becas,operaciones,anulaciones
from financiero.models import SolicitudEgreso,SolicitudBeca
from financiero.consultas import solvente
from reportes import test_financieros as fixture
from reportes.financiero_consultas import generar
from core.paneles import cargar_bandeja,indicadores_direccion,indicadores_administracion
from reportes.presentacion import cuentas_por_estudiante


class PanelesF82Tests(TestCase):
    @classmethod
    def setUpTestData(cls):fixture.FinanzasConsolidadasTests.setUpTestData.__func__(cls)
    def setUp(self):fixture.FinanzasConsolidadasTests.setUp(self)
    crear_donante=fixture.FinanzasConsolidadasTests.crear_donante
    solicitar=fixture.FinanzasConsolidadasTests.solicitar
    aprobar=fixture.FinanzasConsolidadasTests.aprobar
    recibir=fixture.FinanzasConsolidadasTests.recibir
    ingreso=fixture.FinanzasConsolidadasTests.ingreso
    egreso_pendiente=fixture.FinanzasConsolidadasTests.egreso_pendiente
    autorizar_egreso=fixture.FinanzasConsolidadasTests.autorizar_egreso
    egreso=fixture.FinanzasConsolidadasTests.egreso
    pagar=fixture.FinanzasConsolidadasTests.pagar
    flujo=fixture.FinanzasConsolidadasTests.flujo

    def beca_pendiente(self):
        return becas.solicitar(usuario=self.secretaria,matricula_id=self.matricula.pk,porcentaje='50',conceptos=['MENSUALIDAD'],alcance='AMBAS',justificacion='Solicitud ficticia',clave=uuid.uuid4())
    def cancelacion(self):
        s=SesionClase.objects.create(curso=self.cursos[0],numero_clase=1,fecha=date(2026,2,1),hora_inicio=time(8),hora_fin=time(9),estado='PROGRAMADA')
        return academicas.solicitar(sesion_id=s.pk,usuario=self.docente,motivo='Cancelación ficticia',clave=uuid.uuid4())

    def test_indicadores_academicos_son_conteos_de_fuente(self):
        p=indicadores_direccion(self.directora)
        self.assertEqual(p['activos'],1);self.assertEqual(len(p['cursos']),6)
        self.assertEqual(p['inscripciones'],6);self.assertEqual(dict(p['estados']),{'Cursando':6})

    def test_activos_no_confunde_exp_administrativo_con_solvencia(self):
        Estudiante.objects.create(codigo_estudiante='INACT-F82',nombres='Ficticio',apellidos='Inactivo',fecha_ingreso=self.ciclo.fecha_inicio,estado='INACTIVO')
        p=indicadores_direccion(self.directora)
        self.assertEqual(p['activos'],1);self.assertEqual(p['expedientes'],2)

    def test_solvencia_directora_reutiliza_excepcion_f6(self):
        self.aprobar();p=indicadores_direccion(self.directora)
        self.assertTrue(solvente(self.estudiante));self.assertEqual(p['solventes'],1);self.assertEqual(p['insolventes'],0)

    def test_panel_administracion_concilia_con_f7(self):
        self.flujo();p=indicadores_administracion(self.admin,{'desde':None,'hasta':None})
        self.assertEqual([t['valor'] for t in p['periodo']],['USD 60.00','USD 5.00','USD 55.00'])
        self.assertEqual(p['actuales'][0]['valor'],'USD 100.00')
        self.assertEqual(p['cajas_abiertas'],1)

    def test_periodo_no_filtra_saldos_actuales(self):
        self.flujo();p=indicadores_administracion(self.admin,{'desde':timezone.localdate()+timedelta(days=1)})
        self.assertEqual(p['periodo'][0]['valor'],'USD 0.00');self.assertEqual(p['actuales'][0]['valor'],'USD 100.00')

    def test_administracion_no_recibe_bandeja_ni_puede_invocar_adaptador(self):
        with self.assertRaises(PermissionDenied):cargar_bandeja(self.admin)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('direccion_pendientes')).status_code,403)

    def test_bandeja_rechaza_roles_no_directora(self):
        for rol in ('SECRETARIA','MAESTRO','ESTUDIANTE','PASTOR_PRINCIPAL','ADMINISTRADOR'):
            u=Usuario.objects.create_user('f82-'+rol.lower(),rol.lower()+'@example.test','ficticia',rol=rol)
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse('direccion_pendientes')).status_code,403)
            with self.assertRaises(PermissionDenied):cargar_bandeja(u)

    def test_bandeja_anonima_y_cuenta_inactiva(self):
        self.client.logout();self.assertEqual(self.client.get(reverse('direccion_pendientes')).status_code,302)
        self.directora.estado_cuenta='INACTIVA';self.directora.save(update_fields=['estado_cuenta'])
        with self.assertRaises(PermissionDenied):indicadores_direccion(self.directora)

    def test_no_fuga_panel_a_secretaria_maestro_y_pastor(self):
        for u in (self.secretaria,self.docente):
            self.client.force_login(u);r=self.client.get(reverse('dashboard'))
            self.assertNotIn('panel_rol',r.context);self.assertNotContains(r,'Solvencia actual');self.assertNotContains(r,'Ingresos efectivos')

    def test_bandeja_unica_por_origen_con_ids_coincidentes(self):
        b=self.beca_pendiente();e=self.egreso_pendiente();a=self.cancelacion()
        filas=cargar_bandeja(self.directora);claves=[r['clave'] for r in filas]
        self.assertEqual(len(claves),len(set(claves)))
        self.assertIn(f'BECA:{b.pk}',claves);self.assertIn(f'EGRESO:{e.pk}',claves)
        self.assertIn(f'CANCELACION_SESION:{a.pk}',claves)

    def test_egreso_aprobado_sin_desembolso_se_mantiene_en_seguimiento(self):
        s=self.autorizar_egreso(self.egreso_pendiente());filas=cargar_bandeja(self.directora)
        r=next(r for r in filas if r['clave']==f'EGRESO:{s.pk}')
        self.assertEqual(r['estado'],'APROBADA');self.assertTrue(r['atencion'])
        self.assertEqual(r['etapa'],'Seguimiento de desembolso')
        self.assertEqual(sum(f['clave']==r['clave'] for f in filas),1)

    def test_padrinazgo_vencido_conserva_estado_y_proteccion(self):
        s=self.aprobar(self.solicitar(limite=timezone.localdate()-timedelta(days=1)))
        filas=cargar_bandeja(self.directora);r=next(r for r in filas if r['clave']==f'PADRINAZGO:{s.pk}')
        self.assertTrue(r['atencion']);self.assertEqual(r['estado'],'APROBADA')
        self.assertEqual(r['url'],reverse('aportes_revision',args=[s.pk]));self.assertTrue(solvente(self.estudiante))
        self.assertEqual(indicadores_direccion(self.directora)['padrinazgos_vencidos'],1)

    def test_padrinazgo_vigente_no_se_inventa_como_pendiente(self):
        self.aprobar();r=next(r for r in cargar_bandeja(self.directora) if r['tipo']=='PADRINAZGO')
        self.assertFalse(r['atencion'])

    def test_anulacion_pago_explica_efecto_y_abre_expediente_original(self):
        pago=self.pagar();s=anulaciones.solicitar(usuario=self.secretaria,pago_id=pago.pk,clave=uuid.uuid4(),motivo='Ficticio')
        r=next(r for r in cargar_bandeja(self.directora) if r['tipo']=='ANULACION_PAGO')
        self.assertEqual(r['url'],reverse('anulaciones_detalle',args=[s.pk]));self.assertIn('no devuelve dinero',r['consecuencia'])

    def test_rechazo_aparece_solo_en_historial(self):
        s=self.egreso_pendiente();operaciones.decidir_egreso(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',resolucion='No procede')
        self.client.force_login(self.directora)
        self.assertEqual(self.client.get(reverse('direccion_pendientes')).context['cantidad'],0)
        r=self.client.get(reverse('direccion_pendientes'),{'vista':'HISTORIAL','estado':'RECHAZADA'})
        self.assertEqual(r.context['cantidad'],1);self.assertContains(r,'No procede')

    def test_filtros_tipo_busqueda_y_fechas(self):
        self.beca_pendiente();self.egreso_pendiente();self.client.force_login(self.directora)
        url=reverse('direccion_pendientes')
        r=self.client.get(url,{'tipo':'BECA','q':self.estudiante.codigo_estudiante,'desde':str(timezone.localdate())})
        self.assertEqual(r.context['cantidad'],1)
        self.assertEqual(self.client.get(url,{'desde':'2099-01-01'}).context['cantidad'],0)
        for datos in ({'tipo':'OTRO'},{'estado':'FALSO'},{'desde':'2027-01-01','hasta':'2026-01-01'}):
            self.assertEqual(self.client.get(url,datos).status_code,400)

    def test_get_manipulado_no_aprueba_y_post_es_rechazado(self):
        s=self.beca_pendiente();self.client.force_login(self.directora);url=reverse('direccion_pendientes')
        self.assertEqual(self.client.get(url,{'decision':'APROBADA','solicitud_id':s.pk}).status_code,200)
        self.assertEqual(self.client.post(url,{'decision':'APROBADA','solicitud_id':s.pk}).status_code,405)
        s.refresh_from_db();self.assertEqual(s.estado,'PENDIENTE')

    def test_consultas_sin_escritura_y_sin_cache_publico(self):
        self.beca_pendiente();self.client.force_login(self.directora)
        for url in (reverse('dashboard'),reverse('direccion_pendientes')):
            with CaptureQueriesContext(connection) as qs:r=self.client.get(url)
            self.assertEqual(r.status_code,200);self.assertIn('no-store',r.headers['Cache-Control'])
            self.assertFalse([q for q in qs if q['sql'].lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER'))])

    def test_conteo_consultas_no_crece_por_solicitud(self):
        self.egreso_pendiente()
        with CaptureQueriesContext(connection) as uno:cargar_bandeja(self.directora)
        for n in range(24):self.egreso_pendiente(concepto=f'Egreso ficticio {n}')
        with CaptureQueriesContext(connection) as muchos:cargar_bandeja(self.directora)
        self.assertLessEqual(len(muchos),len(uno)+1)

    def test_paginacion_y_filtros_preservados(self):
        for n in range(23):self.egreso_pendiente(concepto=f'Egreso ficticio {n}')
        self.client.force_login(self.directora)
        r=self.client.get(reverse('direccion_pendientes'),{'tipo':'EGRESO','page':'2'})
        self.assertEqual(len(r.context['pagina']),3);self.assertEqual(r.context['cantidad'],23)
        self.assertContains(r,'tipo=EGRESO');self.assertContains(r,'Páginas superior')

    def test_errores_de_fuente_no_muestran_indicadores_parciales(self):
        self.client.force_login(self.directora)
        with patch('core.paneles_views.indicadores_direccion',side_effect=DatabaseError('secreto')):
            r=self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code,503);self.assertNotContains(r,'secreto',status_code=503)
        self.assertNotContains(r,'Asuntos por revisar',status_code=503)
        with patch('core.paneles_views.cargar_bandeja',side_effect=DatabaseError('secreto')):
            self.assertEqual(self.client.get(reverse('direccion_pendientes')).status_code,503)

    def test_admin_fechas_invalidas_no_muestra_totales(self):
        self.client.force_login(self.admin)
        r=self.client.get(reverse('dashboard'),{'desde':'2027-01-01','hasta':'2026-01-01'})
        self.assertEqual(r.status_code,400);self.assertNotContains(r,'Resultado de efectivo',status_code=400)

    def test_cuentas_agrupa_sin_perder_columnas_ni_sumar_dos_veces(self):
        datos=generar('cuentas',{});grupos=cuentas_por_estudiante(datos)
        self.assertEqual(len(grupos),1);g=grupos[0]
        self.assertEqual(g['saldo'],'USD 120.00');self.assertEqual(len(g['obligaciones']),6)
        self.assertEqual(sum(len(o['celdas']) for o in g['obligaciones']),len(datos['filas'])*len(datos['columnas']))

    def test_cuentas_detalle_conserva_todos_los_campos_y_url(self):
        self.client.force_login(self.directora)
        r=self.client.get(reverse('finanzas_reporte',args=['cuentas']))
        self.assertContains(r,'Ver 6 obligaciones y conciliación')
        self.assertContains(r,'USD 120.00');self.assertContains(r,reverse('finanzas_cuenta',args=[self.estudiante.pk]))
        self.assertEqual(r.context['cantidad'],6);self.assertEqual(r.context['cantidad_estudiantes'],1)

    def test_cuentas_csv_e_impresion_conservan_filas_originales(self):
        self.client.force_login(self.directora);url=reverse('finanzas_reporte',args=['cuentas'])
        r=self.client.get(url,{'formato':'csv'});self.assertEqual(r.status_code,200)
        self.assertIn(b'USD 120.00',r.content)
        r=self.client.get(url,{'formato':'imprimir'});self.assertEqual(len(r.context['filas_visibles']),6)
        self.assertNotContains(r,'f82-cuentas')
        for nombre in generar('cuentas',{})['columnas']:self.assertContains(r,nombre)

    def test_agrupar_por_expediente_no_por_nombre(self):
        datos=generar('cuentas',{});fila=datos['filas'][0]
        datos['filas'].append({'celdas':fila['celdas'][:],'url':'/finanzas/estudiantes/999/'})
        grupos=cuentas_por_estudiante(datos);self.assertEqual(len(grupos),2)

    def test_filtro_cuentas_no_inventa_saldo_global_fuera_de_seleccion(self):
        self.client.force_login(self.directora)
        r=self.client.get(reverse('finanzas_reporte',args=['cuentas']),{'estado':'SALDADA'})
        self.assertEqual(r.context['cantidad_estudiantes'],0);self.assertEqual(r.context['saldo_seleccion'],'USD 0.00')
        self.assertContains(r,'No se encontraron registros')


class CorreccionEnBandejaF82Tests(TestCase):
    """El adaptador muestra la propuesta del servicio; no vuelve a calcularla."""
    @classmethod
    def setUpTestData(cls):
        from academico.test_correcciones import CorreccionesTests
        CorreccionesTests.setUpTestData.__func__(cls)

    def setUp(self):
        from academico.test_correcciones import CorreccionesTests
        CorreccionesTests.setUp(self)

    from academico.test_correcciones import CorreccionesTests as _base
    recargar = _base.recargar
    componentes = _base.componentes
    solicitar = _base.solicitar
    aprobar = _base.aprobar

    def test_correccion_muestra_propuesta_original_sin_reabrir_curso(self):
        s = self.solicitar()
        filas = cargar_bandeja(self.directora)
        r = next(r for r in filas if r['clave'] == f'CORRECCION_CALIFICACION:{s.pk}')
        self.assertIn('71.00', r['consecuencia'])
        self.assertIn('APROBADA', r['consecuencia'])
        self.assertEqual(r['url'], reverse('solicitud_academica', args=[s.pk]))
        self.recargar()
        self.assertEqual(self.curso.estado, 'FINALIZADO')
        self.assertEqual(self.nota.nota_final, Decimal('70'))

    def test_correccion_resuelta_conserva_historial_en_bandeja(self):
        s = self.solicitar()
        self.aprobar(s)
        antes = SolicitudAcademica.objects.values().get(pk=s.pk)
        self.client.force_login(self.directora)
        r = self.client.get(reverse('direccion_pendientes'), {'vista': 'HISTORIAL', 'tipo': 'CORRECCION_CALIFICACION'})
        self.assertEqual(r.context['cantidad'], 1)
        self.assertContains(r, 'Resuelta')
        self.assertEqual(SolicitudAcademica.objects.values().get(pk=s.pk), antes)
