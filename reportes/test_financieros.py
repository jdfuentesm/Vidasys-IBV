"""F7: dinero sintético y SQLite en memoria; sin escrituras de reportes."""
import csv
import io
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.db import connection,DatabaseError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from core.models import Usuario
from academico.models import Estudiante
from financiero import test_aportes as fixtures
from financiero import test_operaciones as f5
from financiero import test_caja as f4
from financiero import operaciones,caja,becas,aportes
from financiero.consultas import solvente
from financiero.lectura import EstadoFinanciero
from financiero.models import (Ingreso,Egreso,MovimientoCaja,Caja,SolicitudEgreso,Donacion,Obligacion,
    Beca,AplicacionBeca,DetallePago,ConvenioPago,CuotaConvenio)
from .financiero_forms import REPORTES
from .financiero_fuentes import cargar_dinero
from .financiero_consultas import generar


class FinanzasConsolidadasTests(TestCase):
    @classmethod
    def setUpTestData(cls):fixtures.AportesTests.setUpTestData.__func__(cls)
    def setUp(self):fixtures.AportesTests.setUp(self)
    crear_donante=fixtures.AportesTests.crear_donante
    solicitar=fixtures.AportesTests.solicitar
    aprobar=fixtures.AportesTests.aprobar
    recibir=fixtures.AportesTests.recibir
    pago_pad=fixtures.AportesTests.pago_pad
    revisar=fixtures.AportesTests.revisar
    anular=fixtures.AportesTests.anular

    def ingreso(self,**kw):return f5.OperacionesTests.ingreso(self,**kw)
    def egreso_pendiente(self,**kw):return f5.OperacionesTests.solicitar(self,**kw)
    def autorizar_egreso(self,s):return f5.OperacionesTests.aprobar(self,s)
    def egreso(self):
        s=self.autorizar_egreso(self.egreso_pendiente())
        return f5.OperacionesTests.desembolsar(self,s)
    def pagar(self,**kw):return f4.CajaTests.pagar(self,**kw)
    def convenio(self):return f4.CajaTests.convenio(self)
    def abonar(self,c,**kw):return f4.CajaTests.abonar(self,c,**kw)
    def url(self,tipo='panel',**f):
        from urllib.parse import urlencode
        return reverse('finanzas_reporte',args=[tipo])+('?' + urlencode(f) if f else '')
    def reporte(self,tipo,**f):return generar(tipo,f)
    def totales(self,tipo,**f):return dict(self.reporte(tipo,**f)['totales'])
    def flujo(self):
        self.pagar();self.ingreso();self.recibir(monto='10');self.egreso()

    def test_totales_dinero_real_y_resultado_sin_fondo(self):
        self.flujo();t=self.totales('resultados')
        self.assertEqual(t['Ingresos vigentes verificados'],60)
        self.assertEqual(t['Egresos desembolsados vigentes'],5)
        self.assertEqual(t['Resultado de la selección'],55)
        self.assertEqual(Decimal(caja.totales(self.caja)['esperado']),65)

    def test_donacion_multidestino_solo_un_ingreso_no_lineas_o_caja(self):
        self.recibir(modalidad='DIRIGIDA',matricula_id=self.matricula.pk,monto='40',asignaciones=[(pk,Decimal('20')) for pk in self.ids[:2]])
        self.assertEqual(Donacion.objects.count(),2)
        d,_=cargar_dinero({});self.assertEqual(len(d),1)
        self.assertEqual(d[0].origen,'DON_DIRIGIDA');self.assertEqual(d[0].importe,40)
        self.assertEqual(self.totales('resultados')['Ingresos vigentes verificados'],40)

    def test_convenio_no_duplica_pago_aplicaciones_y_cuotas(self):
        c=self.convenio();self.abonar(c,total=False)
        d,_=cargar_dinero({});self.assertEqual(sum(m.importe for m in d),20)
        self.assertTrue(all(m.origen=='CONVENIO' for m in d))
        self.assertEqual(self.totales('resultados')['Ingresos vigentes verificados'],20)
        r=self.reporte('convenios');self.assertEqual(len(r['filas']),1)
        self.assertEqual(r['filas'][0]['celdas'][4:8],[Decimal('20'),Decimal('100'),Decimal('100'),Decimal('0')])

    def test_compromiso_padrino_no_es_ingreso(self):
        self.aprobar();self.assertEqual(self.totales('resultados')['Ingresos vigentes verificados'],0)
        b=self.totales('beneficios');self.assertEqual(b['Padrinazgos comprometidos históricos'],120)
        self.assertEqual(b['Aportes recibidos aplicados'],0);self.assertEqual(b['Protección actual de la selección'],120)
        self.assertFalse(Ingreso.objects.exists())

    def test_padrinazgo_recibido_reduce_pendiente_sin_sumar_compromiso(self):
        s=self.aprobar();self.pago_pad(s,monto='20',asignaciones=[(self.ids[0],Decimal('20'))])
        b=self.totales('beneficios');self.assertEqual(b['Aportes recibidos aplicados'],20)
        self.assertEqual(b['Compromisos activos pendientes'],100)
        self.assertEqual(self.totales('resultados')['Ingresos vigentes verificados'],20)
        self.assertEqual(self.totales('cuentas')['Saldo financiero pendiente'],100)

    def test_beca_exonera_sin_egreso_ni_recibo(self):
        s=becas.solicitar(usuario=self.secretaria,matricula_id=self.matricula.pk,porcentaje='100',conceptos=['MATRICULA','MENSUALIDAD'],alcance='AMBAS',justificacion='Ficticio',clave=uuid.uuid4())
        # Se utiliza el servicio institucional con su confirmación, sin atajos del reporte.
        datos=dict(usuario=self.directora,solicitud_id=s.pk,porcentaje='100',conceptos=['MATRICULA','MENSUALIDAD'],obligaciones=self.ids,alcance='AMBAS',observaciones='Ficticio')
        _,revision=becas.previsualizar(**datos)
        becas.resolver(**datos,decision='APROBADA',revision=revision)
        self.assertEqual(self.totales('beneficios')['Becas exoneradas'],120)
        self.assertEqual(self.totales('resultados')['Resultado de la selección'],0)
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_distribucion_excluyente_concilia_y_no_duplica_convenio(self):
        self.aprobar(self.solicitar(asignaciones=[(self.ids[0],Decimal('20'))]))
        t=self.totales('cuentas')
        self.assertEqual(t['Saldo financiero pendiente'],120)
        self.assertEqual(t['Protección pendiente efectiva'],20)
        self.assertEqual(t['A cargo del estudiante, incluido convenio y no vencido'],100)
        self.assertEqual(t['Control: padrinazgo + convenio + directo'],120)
        self.assertEqual(len(self.reporte('cuentas')['filas']),6)

    def test_convenio_distribucion_no_nueva_deuda(self):
        self.convenio();t=self.totales('cuentas')
        self.assertEqual(t['Saldo financiero pendiente'],120);self.assertEqual(t['Saldo en convenio'],120)
        self.assertEqual(t['Saldo directo del estudiante'],0)
        self.assertEqual(t['Control: padrinazgo + convenio + directo'],120)

    def test_solvencia_portal_f6_y_categoria_excluyente(self):
        self.aprobar();self.assertTrue(solvente(self.estudiante))
        r=self.reporte('solvencia');self.assertEqual(len(r['filas']),1)
        self.assertEqual(r['filas'][0]['celdas'][1],'Solvente por padrinazgo')
        self.assertEqual(dict(r['totales'])['Estudiantes distintos de la selección'],1)
        self.assertNotIn('DIRECCION-RESERVADA',str(r))

    def test_solvencia_insolvente_y_por_convenio(self):
        self.assertFalse(solvente(self.estudiante));self.assertEqual(EstadoFinanciero().solvencias[self.estudiante.pk]['clase'],'INSOLVENTE')
        self.convenio();self.assertTrue(solvente(self.estudiante));self.assertEqual(EstadoFinanciero().solvencias[self.estudiante.pk]['clase'],'CONVENIO')

    def test_anulacion_excluida_y_efectivo_retenido_conservado(self):
        r=self.recibir();self.anular(r)
        t=self.totales('resultados');self.assertEqual(t['Ingresos vigentes verificados'],0)
        self.assertEqual(t['Operaciones anuladas (informativo, no sumar)'],20)
        c=self.reporte('cajas')['filas'][0]['celdas']
        self.assertEqual(c[8],30);self.assertEqual(c[11],20)
        a=self.reporte('auditoria');self.assertTrue(any(r['celdas'][2]=='ANULADO' for r in a['filas']))

    def test_transferencias_aparte_del_efectivo(self):
        self.recibir(metodo='TRANSFERENCIA');r=self.reporte('cajas')['filas'][0]['celdas']
        self.assertEqual(r[6],0);self.assertEqual(r[8],10);self.assertEqual(r[12],20)
        self.assertEqual(self.totales('resultados')['Ingresos vigentes verificados'],20)

    def test_egreso_autorizado_no_desembolsado_no_es_gasto(self):
        self.autorizar_egreso(self.egreso_pendiente(monto='99'))
        self.assertEqual(self.totales('resultados')['Egresos desembolsados vigentes'],0)
        p=self.reporte('panel');tarjetas={t['titulo']:t for t in p['tarjetas_actuales']}
        self.assertEqual(tarjetas['Importe autorizado aún sin desembolsar']['valor'],'USD 99.00')
        self.client.force_login(self.directora)
        r=self.client.get(tarjetas['Importe autorizado aún sin desembolsar']['url'])
        self.assertEqual(r.status_code,200);self.assertEqual(r.context['cantidad'],1)

    def test_fotografia_cerrada_no_recalculada(self):
        self.recibir();datos=dict(usuario=self.secretaria,caja_id=self.caja.pk,contado='30')
        _,rev=caja.preparar_cierre(**datos);caja.cerrar(**datos,revision=rev)
        self.caja.refresh_from_db();foto=self.caja.cierre.copy()
        Ingreso.objects.update(estado='ANULADO')
        r=self.reporte('cajas')['filas'][0]['celdas']
        self.assertEqual(r[8],30);self.assertEqual(r[11],0)
        self.caja.refresh_from_db();self.assertEqual(self.caja.cierre,foto)

    def test_foto_antigua_sin_campos_no_inventa_cero(self):
        datos=dict(usuario=self.secretaria,caja_id=self.caja.pk,contado='10')
        _,rev=caja.preparar_cierre(**datos);caja.cerrar(**datos,revision=rev)
        Caja.objects.filter(pk=self.caja.pk).update(cierre={'esperado':'10.00'})
        r=self.reporte('cajas');self.assertIsNone(r['filas'][0]['celdas'][6]);self.assertTrue(r['avisos'])

    def test_filtros_operacion_fecha_metodo_categoria_operador(self):
        self.ingreso();self.recibir(metodo='TRANSFERENCIA')
        self.assertEqual(self.totales('resultados',metodo='TRANSFERENCIA')['Ingresos vigentes verificados'],20)
        self.assertEqual(self.totales('resultados',categoria=f'I:{self.ci.pk}')['Ingresos vigentes verificados'],30)
        self.assertEqual(self.totales('resultados',operador=self.directora)['Ingresos vigentes verificados'],0)
        self.assertEqual(self.totales('resultados',desde=timezone.localdate()+timedelta(days=1))['Ingresos vigentes verificados'],0)

    def test_ciclo_no_atribuye_ingreso_general_ni_egreso(self):
        self.flujo();t=self.totales('resultados',ciclo=self.ciclo)
        self.assertEqual(t['Ingresos vigentes verificados'],20);self.assertEqual(t['Egresos desembolsados vigentes'],0)

    def test_filtros_saldo_no_fingen_corte_historico(self):
        self.client.force_login(self.directora)
        r=self.client.get(self.url('cuentas',hasta='2020-01-01'))
        self.assertEqual(r.status_code,400);self.assertContains(r,'saldos históricos',status_code=400)
        self.assertNotContains(r,'USD 120.00',status_code=400)

    def test_filtros_invalidos_fechas_y_ids(self):
        self.client.force_login(self.directora)
        for p in [dict(desde='2026-03-01',hasta='2026-01-01'),dict(estudiante='999999'),dict(categoria='I:999999'),dict(origen='INVALIDO')]:
            with self.subTest(p=p):self.assertEqual(self.client.get(self.url('resultados',**p)).status_code,400)

    def test_todos_reportes_y_formatos_para_directora_y_administrador(self):
        self.flujo()
        for u in (self.directora,self.admin):
            self.client.force_login(u)
            for t in REPORTES:
                for formato in ('html','csv','imprimir'):
                    with self.subTest(rol=u.rol,t=t,formato=formato):
                        r=self.client.get(self.url(t,formato=formato,**({'desde':'','hasta':''} if 'desde' in REPORTES[t][1] else {})))
                        self.assertEqual(r.status_code,200)
                        self.assertIn('no-store',r.headers['Cache-Control'])

    def test_roles_sin_acceso_incluye_csv_y_url_directa(self):
        pastor=Usuario.objects.create_user('f7-pastor','p@example.test','ficticia',rol='PASTOR_PRINCIPAL')
        alumno=Usuario.objects.create_user('f7-alumno','e@example.test','ficticia',rol='ESTUDIANTE')
        for u in (self.secretaria,self.docente,pastor,alumno):
            self.client.force_login(u)
            for t in REPORTES:
                for formato in ('html','csv','imprimir'):
                    self.assertEqual(self.client.get(self.url(t,formato=formato)).status_code,403)

    def test_anonimo_inactivo_y_superuser_otro_rol(self):
        self.client.logout();self.assertEqual(self.client.get(self.url()).status_code,302)
        self.secretaria.is_superuser=True;self.secretaria.save(update_fields=['is_superuser'])
        self.client.force_login(self.secretaria);self.assertEqual(self.client.get(self.url()).status_code,403)
        self.directora.estado_cuenta='INACTIVA';self.directora.save(update_fields=['estado_cuenta'])
        self.client.force_login(self.directora);self.assertEqual(self.client.get(self.url()).status_code,302)

    def test_post_no_permitido_y_get_no_escribe(self):
        self.flujo();self.client.force_login(self.directora)
        for t in REPORTES:
            self.assertEqual(self.client.post(self.url(t),{}).status_code,405)
            with CaptureQueriesContext(connection) as consultas:r=self.client.get(self.url(t))
            self.assertEqual(r.status_code,200)
            escrituras=[q['sql'] for q in consultas if q['sql'].lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER','DROP'))]
            self.assertEqual(escrituras,[])

    def test_csv_neutraliza_formulas_y_conserva_filtros(self):
        self.ci.nombre='=HYPERLINK("evil")';self.ci.save(update_fields=['nombre']);self.ingreso()
        self.client.force_login(self.directora)
        r=self.client.get(self.url('resultados',formato='csv',categoria=f'I:{self.ci.pk}',desde='',hasta=''))
        self.assertEqual(r.status_code,200);rows=list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
        self.assertTrue(any(c.startswith("'=HYPERLINK") for row in rows for c in row))
        self.assertTrue(any(row and row[0]=='Categoría' for row in rows))
        self.assertTrue(any('USD 30.00' in row for row in rows))

    def test_datos_privados_donante_no_salen_a_reportes(self):
        self.recibir();self.client.force_login(self.directora)
        for t in REPORTES:
            r=self.client.get(self.url(t,formato='csv'))
            for privado in ('PRIVADO-777','privado@example.test','DIRECCION-RESERVADA','NOTA-PRIVADA'):
                self.assertNotContains(r,privado)

    def test_error_fuente_no_muestra_totales_parciales(self):
        self.client.force_login(self.directora)
        with patch('reportes.financiero_views.generar',side_effect=DatabaseError('privado')):
            r=self.client.get(self.url('resultados'))
        self.assertEqual(r.status_code,503);self.assertNotContains(r,'privado',status_code=503)
        self.assertContains(r,'No se muestran cifras incompletas',status_code=503)

    def test_batch_no_n_mas_uno_por_estudiante(self):
        with CaptureQueriesContext(connection) as uno:EstadoFinanciero()
        base=self.estudiante
        for n in range(12):
            e=Estudiante.objects.create(codigo_estudiante=f'F7-{n}',nombres='Ficticio',apellidos='Reporte',fecha_nacimiento=base.fecha_nacimiento,fecha_ingreso=base.fecha_ingreso,estado='ACTIVO')
        with CaptureQueriesContext(connection) as varios:EstadoFinanciero()
        self.assertLessEqual(len(varios),len(uno)+1)

    def test_pantalla_contiene_etiquetas_y_detalle_responsivo(self):
        self.flujo();self.client.force_login(self.directora)
        r=self.client.get(self.url('resultados'))
        self.assertContains(r,'f7-registro');self.assertNotContains(r,'<table')
        self.assertContains(r,'base de efectivo');self.assertContains(r,'Descargar CSV')
        self.assertContains(r,'Generado:');self.assertContains(r,'USD 55.00')

    def test_panel_navegacion_periodo_vs_saldos(self):
        self.client.force_login(self.directora)
        r=self.client.get(self.url('panel'));self.assertContains(r,'Situación actual')
        self.assertContains(r,'Operaciones del período seleccionado')
        for grupo in ('tarjetas_periodo','tarjetas_actuales'):
            for t in r.context[grupo]:
                self.assertEqual(self.client.get(t['url']).status_code,200,t['titulo'])

    def test_sin_movimientos_estado_vacio_y_saldo_real(self):
        self.client.force_login(self.directora)
        r=self.client.get(self.url('resultados'));self.assertContains(r,'No se encontraron registros')
        self.assertEqual(self.totales('cuentas')['Saldo financiero pendiente'],120)
        self.assertEqual(self.totales('resultados')['Resultado de la selección'],0)

    def test_decimales_exactos_sin_redondeo_binario(self):
        self.recibir(monto='0.10');self.ingreso(monto='0.20')
        self.assertEqual(self.totales('resultados')['Ingresos vigentes verificados'],Decimal('0.30'))

    def test_categorias_matricula_y_mensualidad_exclusivas(self):
        from financiero.servicios import registrar_pago,reservar_recibo
        registrar_pago(usuario=self.secretaria,estudiante=self.estudiante,token=reservar_recibo(self.secretaria,self.estudiante),metodo='EFECTIVO',referencia='dos',aplicaciones=[(self.obligaciones[0].pk,Decimal('20')),(self.mensualidad.pk,Decimal('10'))])
        d,_=cargar_dinero({});self.assertEqual({m.origen for m in d},{'MATRICULA','MENSUALIDAD'})
        self.assertEqual(sum(m.importe for m in d),30)

    def test_anulacion_pago_aparece_auditoria_no_ingreso(self):
        p=self.pagar();s=f4.CajaTests.solicitar(self,pago=p);f4.CajaTests.aprobar(self,s)
        self.assertEqual(self.totales('resultados')['Ingresos vigentes verificados'],0)
        r=self.reporte('auditoria',estado='ANULADO')
        self.assertTrue(any(f['celdas'][5]==p.numero_recibo for f in r['filas']))

    def test_anulacion_egreso_conserva_salida_fisica(self):
        self.ingreso();d=self.egreso()
        s=f5.OperacionesTests.pedir_anulacion(self,r=d,tipo='EGRESO');f5.OperacionesTests.anular(self,s)
        self.assertEqual(self.totales('resultados')['Egresos desembolsados vigentes'],0)
        self.assertEqual(self.reporte('cajas')['filas'][0]['celdas'][7],5)

    def test_historico_sin_trazabilidad_advertido_no_sumado(self):
        # Un Ingreso aislado no demuestra que no representa un cobro ya registrado en Pago.
        i=Ingreso.objects.create(categoria_ingreso=self.ci,fecha_ingreso=self.fecha,fecha_creacion=self.fecha,monto='33',metodo_pago='EFECTIVO',referencia='Origen anterior desconocido',estado='REGISTRADO',usuario_registra=self.secretaria)
        r=self.reporte('resultados');self.assertTrue(r['avisos'])
        self.assertEqual(dict(r['totales'])['Ingresos vigentes verificados'],0)
        self.assertEqual(dict(r['totales'])['Importes sin conciliación excluidos'],33)
        self.assertEqual(Ingreso.objects.get(pk=i.pk).estado,'REGISTRADO')

    def test_recepcion_donacion_general_no_cambia_saldos_estudiante(self):
        self.recibir();self.assertEqual(self.totales('cuentas')['Saldo financiero pendiente'],120)
        self.assertEqual(self.totales('beneficios')['Aportes recibidos aplicados'],0)

    def test_beneficiarios_combinados_no_duplican_estudiante(self):
        # Beca a matrícula y padrinazgo a las otras cinco obligaciones, sin cruzar coberturas.
        s=becas.solicitar(usuario=self.secretaria,matricula_id=self.matricula.pk,porcentaje='100',conceptos=['MATRICULA'],alcance='AMBAS',justificacion='Ficticio',clave=uuid.uuid4())
        datos=dict(usuario=self.directora,solicitud_id=s.pk,porcentaje='100',conceptos=['MATRICULA'],alcance='AMBAS',obligaciones=[self.ids[0]],observaciones='Ficticio')
        _,rev=becas.previsualizar(**datos);becas.resolver(**datos,decision='APROBADA',revision=rev)
        self.aprobar(self.solicitar(asignaciones=[(pk,Decimal('20')) for pk in self.ids[1:]]))
        ctx=EstadoFinanciero();self.assertEqual(ctx.solvencias[self.estudiante.pk]['clase'],'COMBINADA')
        self.assertEqual(self.totales('beneficios')['Estudiantes beneficiados distintos'],1)
        self.assertEqual(self.totales('cuentas')['Saldo financiero pendiente'],100)
        self.assertEqual(self.totales('solvencia')['Estudiantes distintos de la selección'],1)

    def test_compromiso_vencido_proteccion_no_se_retira_automaticamente(self):
        self.aprobar(self.solicitar(limite=timezone.localdate()-timedelta(days=1)))
        b=self.totales('beneficios',estado='VENCIDO');self.assertEqual(b['Compromisos activos pendientes'],120)
        self.assertTrue(solvente(self.estudiante));self.assertEqual(b['Protección actual de la selección'],120)

    def test_solicitudes_y_resoluciones_fechas_y_operador(self):
        s=self.solicitar();r=self.reporte('auditoria',estado='PENDIENTE',operador=self.secretaria)
        self.assertEqual(len(r['filas']),1);self.assertEqual(r['filas'][0]['celdas'][3],self.secretaria.numero_usuario)
        self.aprobar(s);r=self.reporte('auditoria',estado='APROBADA',operador=self.directora)
        self.assertEqual(len(r['filas']),1)
        self.assertFalse(self.reporte('auditoria',estado='APROBADA',operador=self.secretaria)['filas'])

    def test_filtro_estado_anulado_no_reincorpora_dinero(self):
        r=self.recibir();self.anular(r)
        t=self.totales('resultados',estado='ANULADO');self.assertEqual(t['Ingresos vigentes verificados'],0)
        self.assertEqual(t['Operaciones anuladas (informativo, no sumar)'],20)

    def test_csv_imprimir_paginacion_mismo_alcance(self):
        self.flujo();self.client.force_login(self.directora)
        for formato in ('html','csv','imprimir'):
            r=self.client.get(self.url('resultados',formato=formato,metodo='TRANSFERENCIA',desde='',hasta=''))
            self.assertEqual(r.status_code,200)
            if formato!='csv':self.assertEqual(r.context['cantidad'],0)
            self.assertNotContains(r,'USD 55.00')

    def test_historiales_extensos_paginar_sin_perder_exportacion(self):
        for n in range(27):self.ingreso(concepto=f'Ingreso ficticio {n}',referencia=str(n))
        self.client.force_login(self.directora)
        r=self.client.get(self.url('resultados'));self.assertEqual(r.context['cantidad'],27)
        self.assertEqual(len(r.context['filas_visibles']),25)
        r=self.client.get(self.url('resultados',formato='imprimir'));self.assertEqual(len(r.context['filas_visibles']),27)

    def test_head_y_formatos_desconocidos(self):
        self.client.force_login(self.directora)
        self.assertEqual(self.client.head(self.url()).status_code,200)
        self.assertEqual(self.client.get(self.url('resultados',formato='exe')).status_code,400)
        self.assertEqual(self.client.get(self.url('inventado')).status_code,404)

    def test_auditoria_anulacion_fecha_decision_no_fecha_del_cobro(self):
        r=self.recibir();self.anular(r)
        viejo=timezone.now()-timedelta(days=60)
        Ingreso.objects.filter(pk=r.ingreso_id).update(fecha_ingreso=viejo)
        a=self.reporte('auditoria',estado='ANULADO',desde=timezone.localdate(),hasta=timezone.localdate(),operador=self.directora)
        self.assertEqual(len(a['filas']),1);self.assertEqual(a['filas'][0]['celdas'][6],20)
        self.assertFalse(self.reporte('auditoria',estado='ANULADO',operador=self.secretaria)['filas'])

    def test_auditoria_pago_varios_conceptos_importe_completo_una_vez(self):
        from financiero.servicios import registrar_pago,reservar_recibo
        p=registrar_pago(usuario=self.secretaria,estudiante=self.estudiante,token=reservar_recibo(self.secretaria,self.estudiante),metodo='EFECTIVO',referencia='dos',aplicaciones=[(self.ids[0],Decimal('20')),(self.mensualidad.pk,Decimal('10'))])[0]
        s=f4.CajaTests.solicitar(self,pago=p);f4.CajaTests.aprobar(self,s)
        a=self.reporte('auditoria',estado='ANULADO')
        self.assertEqual(len(a['filas']),1);self.assertEqual(a['filas'][0]['celdas'][6],30)
