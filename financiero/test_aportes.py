"""F6: compromisos sin ingreso, aportes reales y privacidad; SQLite efímero."""
import uuid
from datetime import date,datetime,timedelta,timezone as tz
from decimal import Decimal
from unittest.mock import patch
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction,IntegrityError,DatabaseError
from django.test import TestCase,Client,RequestFactory
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from core.models import Usuario
from academico.models import Matricula,Estudiante,CicloAcademico,Curso
from academico.flujo import matricular
from . import aportes,caja,becas,convenios
from .consultas import importes,solvente,cuenta,solvente_sql
from .models import (Donante,Donacion,Padrinazgo,RecepcionDonacion,LineaDonacion,CoberturaPadrinazgo,
    SolicitudPadrinazgo,RevisionPadrinazgo,AnulacionDonacion,HistorialDonante,
    Ingreso,MovimientoCaja,Pago,Obligacion,Beca,SolicitudBeca,ConvenioPago,ConvenioObligacion,CuotaConvenio)


class AportesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_operaciones import OperacionesTests
        OperacionesTests.setUpTestData.__func__(cls)

    def setUp(self):
        from .test_operaciones import OperacionesTests
        OperacionesTests.setUp(self)
        self.donante=self.crear_donante()
        self.ids=[o.pk for o in self.obligaciones]
        self.inicio=timezone.localdate()-timedelta(days=10);self.limite=timezone.localdate()+timedelta(days=30)

    def crear_donante(self,**cambios):
        return aportes.guardar_donante(**(dict(usuario=self.secretaria,clave=uuid.uuid4(),tipo='PERSONA',
            nombre_completo='Padrino PRIVADO',documento_identidad='',correo='privado@example.test',telefono='PRIVADO-777',
            pais='SV',direccion='DIRECCION-RESERVADA',es_anonimo=False,notas='NOTA-PRIVADA',estado='ACTIVO')|cambios))

    def solicitar(self,**cambios):
        return aportes.solicitar(**(dict(usuario=self.secretaria,clave=uuid.uuid4(),donante_id=self.donante.pk,
            matricula_id=self.matricula.pk,inicio=self.inicio,limite=self.limite,modalidad='FIJO',
            asignaciones=[(pk,Decimal('20')) for pk in self.ids],observaciones='Compromiso institucional ficticio')|cambios))

    def aprobar(self,s=None,**cambios):
        s=s or self.solicitar();datos=dict(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA')|cambios
        revision=aportes.resolver(**datos)
        return aportes.resolver(**datos,revision=revision,confirmar=True)

    def recibir(self,**cambios):
        return aportes.recibir(**(dict(usuario=self.secretaria,clave=uuid.uuid4(),donante_id=self.donante.pk,
            modalidad='GENERAL',monto='20',fecha=self.fecha,metodo='EFECTIVO',referencia='APORTE-F6')|cambios))

    def pago_pad(self,s,monto='120',**cambios):
        return self.recibir(**(dict(modalidad='PADRINAZGO',matricula_id=self.matricula.pk,solicitud_id=s.pk,
            monto=monto,asignaciones=[(pk,Decimal('20')) for pk in self.ids])|cambios))

    def revisar(self,s,**cambios):
        datos=dict(usuario=self.directora,solicitud_id=s.pk,clave=uuid.uuid4(),accion='PRORROGA',motivo='Resolución ficticia',limite=self.limite+timedelta(days=30))|cambios
        revision=aportes.revisar(**datos);return aportes.revisar(**datos,revision=revision,confirmar=True)

    def anular(self,r,**cambios):
        a=aportes.pedir_anulacion(usuario=self.secretaria,recepcion_id=r.pk,clave=uuid.uuid4(),motivo='Error ficticio')
        datos=dict(usuario=self.directora,anulacion_id=a.pk,decision='APROBADA')|cambios
        revision=aportes.anular(**datos);return aportes.anular(**datos,revision=revision,confirmar=True)

    def test_donante_historial_y_desactivacion(self):
        d=self.crear_donante(donante_id=self.donante.pk,estado='INACTIVO')
        self.assertEqual(d.estado,'INACTIVO');self.assertEqual(HistorialDonante.objects.count(),2)
        with self.assertRaises(ValidationError):self.recibir()

    def test_donante_clave_idempotente_y_datos_diferentes(self):
        clave=uuid.uuid4();d=self.crear_donante(clave=clave)
        self.assertEqual(self.crear_donante(clave=clave).pk,d.pk)
        with self.assertRaises(ValidationError):self.crear_donante(clave=clave,nombre_completo='Otro')

    def test_donante_documento_duplicado_y_permisos(self):
        self.crear_donante(documento_identidad='FICTICIO-1')
        with self.assertRaises(ValidationError):self.crear_donante(documento_identidad='FICTICIO-1')
        for u in (self.directora,self.docente):
            with self.assertRaises(PermissionDenied):self.crear_donante(usuario=u)

    def test_general_un_ingreso_un_movimiento_sin_pagos_academicos(self):
        r=self.recibir();self.assertEqual(Ingreso.objects.count(),1);self.assertEqual(MovimientoCaja.objects.count(),1)
        self.assertEqual(Donacion.objects.get().monto,20);self.assertFalse(Pago.objects.exists())
        self.assertEqual(Decimal(caja.totales(self.caja)['esperado']),30);self.assertTrue(r.numero.startswith('DON-'))

    def test_transferencia_general_no_aumenta_efectivo(self):
        self.recibir(metodo='TRANSFERENCIA');self.assertEqual(Decimal(caja.totales(self.caja)['esperado']),10)

    def test_dirigida_reduce_saldo_real_por_donacion(self):
        r=self.recibir(modalidad='DIRIGIDA',matricula_id=self.matricula.pk,monto='12',asignaciones=[(self.ids[0],Decimal('12'))])
        self.assertEqual(importes(self.obligaciones[0]),(Decimal('0'),Decimal('12'),Decimal('8')))
        self.assertEqual(r.lineas.count(),1)

    def test_multidestino_sin_doble_contabilizar(self):
        self.recibir(modalidad='DIRIGIDA',matricula_id=self.matricula.pk,monto='40',asignaciones=[(pk,Decimal('20')) for pk in self.ids[:2]])
        self.assertEqual(Ingreso.objects.count(),1);self.assertEqual(MovimientoCaja.objects.count(),1)
        self.assertEqual(sum(Donacion.objects.values_list('monto',flat=True)),40)
        self.assertEqual(Donacion.objects.count(),2)

    def test_recepcion_idempotente_y_nueva_clave_duplicada(self):
        clave=uuid.uuid4();r=self.recibir(clave=clave)
        self.assertEqual(self.recibir(clave=clave).pk,r.pk)
        with self.assertRaises(ValidationError):self.recibir(clave=clave,monto='21')
        with self.assertRaises(ValidationError):self.recibir()
        self.assertEqual(Ingreso.objects.count(),1)

    def test_recepcion_caja_cerrada_bloqueada(self):
        t=caja.totales(self.caja);d=dict(usuario=self.secretaria,caja_id=self.caja.pk,contado=t['esperado'])
        _,rev=caja.preparar_cierre(**d);caja.cerrar(**d,revision=rev)
        with self.assertRaises(ValidationError):self.recibir()

    def test_aportes_excedidos_repetidos_o_generales_manipulados(self):
        for cambios in [dict(modalidad='DIRIGIDA',matricula_id=self.matricula.pk,monto='21',asignaciones=[(self.ids[0],Decimal('21'))]),
            dict(modalidad='DIRIGIDA',matricula_id=self.matricula.pk,monto='20',asignaciones=[(self.ids[0],Decimal('10'))]*2),dict(asignaciones=[(self.ids[0],Decimal('20'))])]:
            with self.assertRaises(ValidationError):self.recibir(**cambios)
        self.assertFalse(Ingreso.objects.exists())

    def test_padrinazgo_solicitado_no_protege_ni_ingresa(self):
        self.solicitar();self.assertFalse(solvente(self.estudiante));self.assertFalse(Ingreso.objects.exists());self.assertFalse(Padrinazgo.objects.exists())

    def test_autorizacion_cubre_ciento_veinte_sin_dinero(self):
        s=self.aprobar();self.assertFalse(solvente_sql(self.estudiante));self.assertTrue(solvente(self.estudiante))
        resumen=aportes.detalle_solvencia(self.estudiante)
        self.assertEqual((resumen['saldo_financiero'],resumen['cobertura_autorizada'],resumen['saldo_estudiante']),(120,120,0))
        self.assertFalse(Donacion.objects.exists());self.assertFalse(Ingreso.objects.exists())
        self.assertEqual(s.coberturas.count(),6)

    def test_parcial_no_ignora_obligaciones_vencidas(self):
        self.aprobar(self.solicitar(asignaciones=[(self.ids[0],Decimal('20'))]))
        self.assertFalse(solvente(self.estudiante));self.assertEqual(cuenta(self.estudiante)['cobertura_total'],20)

    def test_porcentaje_y_monto_fijo_no_son_mensualidad(self):
        s=self.aprobar(self.solicitar(modalidad='PORCENTAJE',porcentaje='50'))
        self.assertEqual(sum(s.coberturas.values_list('monto',flat=True)),60)
        self.assertIsNone(s.padrinazgo.monto_mensual);self.assertEqual(s.padrinazgo.porcentaje_cobertura,50)

    def test_no_sobre_cobertura_y_complemento_de_beca(self):
        Obligacion.objects.filter(matricula=self.matricula).update(monto_descuento='10')
        s=self.aprobar(self.solicitar(asignaciones=[(pk,Decimal('10')) for pk in self.ids]))
        self.assertEqual(sum(s.coberturas.values_list('monto',flat=True)),60);self.assertTrue(solvente(self.estudiante))
        with self.assertRaises(ValidationError):self.solicitar(asignaciones=[(self.ids[0],Decimal('1'))])

    def test_dos_padrinos_parciales_sin_exceder_saldo(self):
        self.aprobar(self.solicitar(asignaciones=[(pk,Decimal('10')) for pk in self.ids]))
        otro=self.crear_donante(nombre_completo='Otro padrino')
        self.aprobar(self.solicitar(donante_id=otro.pk,asignaciones=[(pk,Decimal('10')) for pk in self.ids]))
        self.assertTrue(solvente(self.estudiante))

    def test_fecha_inicio_futura_no_protege_y_limite_no_retira_cobertura(self):
        s=self.aprobar(self.solicitar(inicio=timezone.localdate()+timedelta(days=1)))
        self.assertFalse(solvente(self.estudiante))
        Padrinazgo.objects.filter(pk=s.padrinazgo_id).update(fecha_inicio=self.inicio,fecha_fin=timezone.localdate()-timedelta(days=1))
        self.assertTrue(solvente(self.estudiante))

    def test_recepcion_parcial_disminuye_saldo_y_pendiente_no_exigible(self):
        s=self.aprobar();r=self.pago_pad(s,monto='10',asignaciones=[(self.ids[0],Decimal('10'))])
        d=aportes.detalle_solvencia(self.estudiante)
        self.assertEqual((d['saldo_financiero'],d['cobertura_autorizada'],d['saldo_estudiante']),(110,110,0));self.assertTrue(d['solvente'])
        self.assertEqual(Decimal(caja.totales(self.caja)['esperado']),20)

    def test_recebir_total_no_cuenta_dos_veces_compromiso(self):
        s=self.aprobar();r=self.pago_pad(s)
        self.assertEqual(Ingreso.objects.get().monto,120);self.assertEqual(sum(Donacion.objects.values_list('monto',flat=True)),120)
        self.assertEqual(MovimientoCaja.objects.count(),1);self.assertEqual(cuenta(self.estudiante)['saldo_total'],0)
        self.assertEqual(aportes.detalle_solvencia(self.estudiante)['cobertura_autorizada'],0)

    def test_recepcion_de_otro_padrino_o_matricula_denegada(self):
        s=self.aprobar();otro=self.crear_donante(nombre_completo='Otro')
        with self.assertRaises(ValidationError):self.pago_pad(s,donante_id=otro.pk)
        with self.assertRaises(ValidationError):self.recibir(modalidad='DIRIGIDA',matricula_id=self.matricula.pk,asignaciones=[(self.ids[0],Decimal('20'))])

    def test_solo_directora_aprueba_y_rechazo_exige_motivo(self):
        s=self.solicitar()
        for u in (self.secretaria,self.admin,self.docente):
            with self.assertRaises(PermissionDenied):self.aprobar(s,usuario=u)
        with self.assertRaises(ValidationError):self.aprobar(s,decision='RECHAZADA')
        aportes.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',motivo='No procede')
        self.assertFalse(CoberturaPadrinazgo.objects.exists())

    def test_roles_revocados_y_solicitud_obsoleta(self):
        s=self.solicitar();Donante.objects.filter(pk=self.donante.pk).update(estado='INACTIVO')
        with self.assertRaises(ValidationError):self.aprobar(s)
        Donante.objects.filter(pk=self.donante.pk).update(estado='ACTIVO');Usuario.objects.filter(pk=self.secretaria.pk).update(rol='MAESTRO')
        with self.assertRaises(ValidationError):self.aprobar(s)

    def test_aprobacion_reintento_contradictorio(self):
        s=self.aprobar()
        self.assertEqual(aportes.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',confirmar=True).pk,s.pk)
        with self.assertRaises(ValidationError):aportes.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',motivo='Otro')

    def test_prorroga_tras_vencimiento_no_mueve_dinero(self):
        s=self.aprobar();r=self.revisar(s)
        s.padrinazgo.refresh_from_db();self.assertEqual(s.padrinazgo.fecha_fin,self.limite+timedelta(days=30))
        self.assertTrue(solvente(self.estudiante));self.assertFalse(Ingreso.objects.exists())

    def test_sustitucion_preserva_recepcion_del_padrino_anterior(self):
        s=self.aprobar();rec=self.pago_pad(s,monto='5',asignaciones=[(self.ids[0],Decimal('5'))])
        otro=self.crear_donante(nombre_completo='Reemplazo')
        self.revisar(s,accion='SUSTITUCION',limite=None,donante_id=otro.pk)
        rec.refresh_from_db();self.assertEqual(rec.donante_id,self.donante.pk)
        with self.assertRaises(ValidationError):self.pago_pad(s,monto='5',asignaciones=[(self.ids[0],Decimal('5'))],referencia='Otra')
        self.pago_pad(s,monto='5',asignaciones=[(self.ids[0],Decimal('5'))],donante_id=otro.pk,referencia='Reemplazo')

    def test_cancelacion_exige_notificacion_y_cobra_solo_pendiente(self):
        s=self.aprobar();self.pago_pad(s,monto='10',asignaciones=[(self.ids[0],Decimal('10'))])
        with self.assertRaises(ValidationError):self.revisar(s,accion='CANCELACION',limite=None)
        self.revisar(s,accion='CANCELACION',limite=None,notificacion='La cobertura pendiente fue cancelada mediante resolución.')
        self.assertFalse(solvente(self.estudiante));self.assertEqual(cuenta(self.estudiante)['saldo_total'],110)
        self.assertEqual(Donacion.objects.get().estado,'RECIBIDA')

    def test_conversion_beca_cien_reutiliza_f2(self):
        s=self.aprobar();r=self.revisar(s,accion='BECA',limite=None,porcentaje='100',notificacion='Tu cobertura se convirtió en beca.')
        self.assertIsNotNone(r.aplicados['beca']);self.assertEqual(cuenta(self.estudiante)['saldo_total'],0)
        self.assertFalse(Ingreso.objects.exists());self.assertTrue(solvente(self.estudiante))
        self.assertEqual(SolicitudBeca.objects.get().solicitante_id,self.directora.pk)

    def test_conversion_incompatible_restituye_cobertura(self):
        s=self.aprobar();self.pago_pad(s,monto='3',asignaciones=[(self.ids[0],Decimal('3'))])
        with self.assertRaises(ValidationError):self.revisar(s,accion='BECA',limite=None,porcentaje='100',notificacion='Conversión solicitada')
        self.assertEqual(s.coberturas.filter(activa=True).count(),6);self.assertTrue(solvente(self.estudiante));self.assertFalse(Beca.objects.exists())

    def test_conversion_no_acumula_becas_existentes(self):
        Obligacion.objects.filter(matricula=self.matricula).update(monto_descuento='10')
        s=self.aprobar(self.solicitar(asignaciones=[(pk,Decimal('10')) for pk in self.ids]))
        with self.assertRaises(ValidationError):self.revisar(s,accion='BECA',limite=None,porcentaje='50',notificacion='Conversión')
        self.assertTrue(solvente(self.estudiante))

    def test_revision_solo_direccion_y_reintento(self):
        s=self.aprobar()
        with self.assertRaises(PermissionDenied):self.revisar(s,usuario=self.admin)
        clave=uuid.uuid4();r=self.revisar(s,clave=clave)
        self.assertEqual(aportes.revisar(usuario=self.directora,solicitud_id=s.pk,clave=clave,accion='PRORROGA',motivo='Resolución ficticia',limite=self.limite+timedelta(days=30),confirmar=True).pk,r.pk)

    def test_convenios_bloquean_cobertura_y_aporte_dirigido(self):
        c=ConvenioPago.objects.create(estudiante=self.estudiante,usuario_autoriza=self.directora,fecha_convenio=timezone.localdate(),monto_convenido=20,numero_cuotas=1,estado='ACTIVO')
        ConvenioObligacion.objects.create(convenio=c,obligacion=self.obligaciones[0],saldo_incluido=20)
        with self.assertRaises(ValidationError):self.solicitar()
        with self.assertRaises(ValidationError):self.recibir(modalidad='DIRIGIDA',matricula_id=self.matricula.pk,asignaciones=[(self.ids[0],Decimal('20'))])

    def test_pagos_y_becas_no_consumen_cobertura_silenciosamente(self):
        self.aprobar()
        from .test_caja import CajaTests
        with self.assertRaises(ValidationError):CajaTests.pagar(self)
        from .becas import plan,datos_resolucion
        with self.assertRaises(ValidationError):plan(self.matricula,self.obligaciones,datos_resolucion('APROBADA',porcentaje='100',conceptos=['MATRICULA','MENSUALIDAD'],alcance='AMBAS',obligaciones=self.ids))

    def test_rollback_recepcion_revierte_donaciones_y_caja(self):
        s=self.aprobar()
        with patch.object(MovimientoCaja,'save',side_effect=DatabaseError('Ficticio')),self.assertRaises(DatabaseError):self.pago_pad(s)
        self.assertFalse(Ingreso.objects.exists());self.assertFalse(Donacion.objects.exists());self.assertTrue(solvente(self.estudiante))

    def test_rollback_aprobacion_y_revision(self):
        s=self.solicitar()
        with patch.object(CoberturaPadrinazgo,'save',side_effect=DatabaseError('Ficticio')),self.assertRaises(DatabaseError):self.aprobar(s)
        self.assertFalse(Padrinazgo.objects.exists());self.assertEqual(SolicitudPadrinazgo.objects.get(pk=s.pk).estado,'PENDIENTE')

    def test_anulacion_aporte_restablece_deuda_y_cobertura_no_devuelve(self):
        s=self.aprobar();r=self.pago_pad(s);self.anular(r)
        d=aportes.detalle_solvencia(self.estudiante)
        self.assertEqual((d['saldo_financiero'],d['cobertura_autorizada'],d['saldo_estudiante']),(120,120,0))
        self.assertTrue(d['solvente']);self.assertEqual(Decimal(caja.totales(self.caja)['esperado']),130)
        self.assertEqual(Decimal(caja.totales(self.caja)['disponible']),10)

    def test_anulacion_tras_cancelar_cobertura_y_cerrar_caja_bloqueada(self):
        s=self.aprobar();r=self.pago_pad(s,monto='10',asignaciones=[(self.ids[0],Decimal('10'))])
        self.revisar(s,accion='CANCELACION',limite=None,notificacion='Resolución de cancelación')
        with self.assertRaises(ValidationError):self.anular(r)

    def test_anulacion_rechazo_y_permisos(self):
        r=self.recibir();a=aportes.pedir_anulacion(usuario=self.secretaria,recepcion_id=r.pk,clave=uuid.uuid4(),motivo='Error')
        with self.assertRaises(PermissionDenied):aportes.anular(usuario=self.admin,anulacion_id=a.pk,decision='APROBADA')
        with self.assertRaises(ValidationError):aportes.anular(usuario=self.directora,anulacion_id=a.pk,decision='RECHAZADA')
        aportes.anular(usuario=self.directora,anulacion_id=a.pk,decision='RECHAZADA',resolucion='No procede');self.assertEqual(Ingreso.objects.get().estado,'REGISTRADO')

    def test_historial_modelos_inmutables(self):
        r=self.recibir()
        for obj in (r,r.lineas.get(),HistorialDonante.objects.first()):
            with self.assertRaises(ValidationError):obj.save()
            with self.assertRaises(ValidationError):obj.delete()

    def test_portal_protege_academico_sin_exponer_datos_padrino(self):
        s=self.aprobar();u=Usuario.objects.create_user('alumno-f6','alumno@example.test','ficticia',rol='ESTUDIANTE')
        Estudiante.objects.filter(pk=self.estudiante.pk).update(usuario=u);self.client.force_login(u)
        for nombre in ('portal_inicio','portal_cuenta','portal_academico'):
            respuesta=self.client.get(reverse(nombre));self.assertEqual(respuesta.status_code,200)
            for privado in ('Padrino PRIVADO','privado@example.test','PRIVADO-777','DIRECCION-RESERVADA','NOTA-PRIVADA'):self.assertNotContains(respuesta,privado)
        self.assertContains(self.client.get(reverse('portal_inicio')),'SOLVENTE POR PADRINAZGO')
        self.revisar(s,accion='CANCELACION',limite=None,notificacion='Tu cobertura pendiente fue cancelada por resolución de Dirección.')
        self.assertContains(self.client.get(reverse('portal_inicio')),'Tu cobertura pendiente fue cancelada')
        self.assertEqual(self.client.get(reverse('portal_academico')).status_code,403)

    def test_alerta_vencidos_en_dashboard_direccion(self):
        s=self.aprobar();Padrinazgo.objects.filter(pk=s.padrinazgo_id).update(fecha_fin=timezone.localdate()-timedelta(days=1))
        self.client.force_login(self.directora);self.assertContains(self.client.get(reverse('dashboard')),'Padrinazgos pendientes de revisión: 1')
        self.assertTrue(solvente(self.estudiante))

    def test_roles_ajenos_no_acceden_donantes_aportes_o_reportes(self):
        r=self.recibir();s=self.aprobar()
        for rol in ('MAESTRO','ESTUDIANTE','PASTOR_PRINCIPAL'):
            u=Usuario.objects.create_user('f6-'+rol,rol+'@example.test','ficticia',rol=rol);self.client.force_login(u)
            for url in (reverse('aportes_panel'),reverse('aportes_donante',args=[self.donante.pk]),reverse('aportes_solicitud',args=[s.pk]),reverse('aportes_recibo',args=[r.pk]),reverse('aportes_reporte')):
                self.assertEqual(self.client.get(url).status_code,403);self.assertEqual(self.client.post(url,{}).status_code,403)

    def test_admin_no_elude_autorizaciones(self):
        req=RequestFactory().get('/admin/');req.user=self.admin
        for m in (Donante,Donacion,Padrinazgo):
            self.assertFalse(admin.site._registry[m].has_add_permission(req));self.assertFalse(admin.site._registry[m].has_change_permission(req));self.assertFalse(admin.site._registry[m].has_delete_permission(req))

    def test_reporte_csv_y_separacion_compromisos_ingresos(self):
        self.aprobar();self.client.force_login(self.directora);url=reverse('aportes_reporte')
        self.assertEqual(self.client.get(url).context['recibido'],0)
        self.assertIn(b'120',self.client.get(url,{'seccion':'COMPROMISOS'}).content)
        self.recibir();self.assertEqual(self.client.get(url).context['recibido'],20)
        self.assertIn('DON-',self.client.get(url,{'formato':'csv'}).content.decode('utf-8-sig'))

    def test_recepcion_posterior_fin_ciclo_julio_2027(self):
        from .calendario import guardar
        c=CicloAcademico.objects.create(nombre='Último ciclo 2027',numero_ciclo=1,anio=2027,fecha_inicio='2027-01-01',fecha_fin='2027-06-30',estado='ACTIVO')
        datos={'emision':'2027-01-01','matricula':'2027-01-10','meses':['2027-02','2027-03','2027-04','2027-05','2027-06']}
        from .models import ConceptoCobro
        datos.update(concepto_matricula=ConceptoCobro.objects.get(nombre='MATRICULA').pk,concepto_mensualidad=ConceptoCobro.objects.get(nombre='MENSUALIDAD').pk)
        guardar(c,datos)
        c.refresh_from_db()
        for anterior in Curso.objects.filter(ciclo=self.ciclo):Curso.objects.create(materia=anterior.materia,maestro=anterior.maestro,ciclo=c,fecha_inicio=c.fecha_inicio,fecha_fin=c.fecha_fin,modalidad='PRESENCIAL',estado='ACTIVO')
        self.matricula=matricular(estudiante=self.estudiante,ciclo=c,numero_matricula='ULTIMO-2027',fecha_matricula=date(2027,1,2))[0]
        # Cargos del ciclo previo pagados: no se ignoran obligaciones vencidas ajenas a la cobertura.
        Obligacion.objects.exclude(matricula=self.matricula).update(monto_descuento=20)
        self.ids=list(self.matricula.obligaciones.values_list('pk',flat=True));self.obligaciones=list(self.matricula.obligaciones.all())
        with patch('django.utils.timezone.localdate',return_value=date(2027,6,15)),patch('django.utils.timezone.now',return_value=datetime(2027,6,15,12,tzinfo=tz.utc)):
            s=self.aprobar(self.solicitar(inicio=date(2027,1,1),limite=date(2027,7,31)))
            d=aportes.detalle_solvencia(self.estudiante);self.assertTrue(d['solvente']);self.assertEqual((d['saldo_financiero'],d['cobertura_autorizada'],d['saldo_estudiante']),(120,120,0));self.assertFalse(Ingreso.objects.exists())
        CicloAcademico.objects.filter(pk=c.pk).update(estado='FINALIZADO')
        with patch('django.utils.timezone.localdate',return_value=date(2027,7,15)),patch('django.utils.timezone.now',return_value=datetime(2027,7,15,12,tzinfo=tz.utc)):
            self.pago_pad(s,fecha=datetime(2027,7,15,10,tzinfo=tz.utc))
            self.assertEqual(cuenta(self.estudiante)['saldo_total'],0);self.assertEqual(Ingreso.objects.get().monto,120)

    def test_solicitud_uuid_tras_aprobar_no_duplica_cobertura(self):
        clave=uuid.uuid4();s=self.solicitar(clave=clave);self.aprobar(s)
        self.assertEqual(self.solicitar(clave=clave).pk,s.pk)
        with self.assertRaises(ValidationError):self.solicitar(clave=clave,observaciones='Cambiar')
        self.assertEqual(CoberturaPadrinazgo.objects.count(),6)

    def test_aporte_anulacion_reintento_y_doble_solicitud(self):
        r=self.recibir();clave=uuid.uuid4()
        a=aportes.pedir_anulacion(usuario=self.secretaria,recepcion_id=r.pk,clave=clave,motivo='Ficticio')
        self.assertEqual(aportes.pedir_anulacion(usuario=self.secretaria,recepcion_id=r.pk,clave=clave,motivo='Ficticio').pk,a.pk)
        with self.assertRaises(ValidationError):aportes.pedir_anulacion(usuario=self.secretaria,recepcion_id=r.pk,clave=uuid.uuid4(),motivo='Otro')
        revision=aportes.anular(usuario=self.directora,anulacion_id=a.pk,decision='APROBADA')
        aportes.anular(usuario=self.directora,anulacion_id=a.pk,decision='APROBADA',revision=revision,confirmar=True)
        self.assertEqual(aportes.anular(usuario=self.directora,anulacion_id=a.pk,decision='APROBADA',confirmar=True).pk,a.pk)
        with self.assertRaises(ValidationError):aportes.anular(usuario=self.directora,anulacion_id=a.pk,decision='RECHAZADA',resolucion='Otra')

    def test_caja_cerrada_preserva_foto_al_intentar_anular(self):
        r=self.recibir();t=caja.totales(self.caja);d=dict(usuario=self.secretaria,caja_id=self.caja.pk,contado=t['esperado'])
        _,rev=caja.preparar_cierre(**d);c=caja.cerrar(**d,revision=rev);foto=c.cierre
        with self.assertRaises(ValidationError):self.anular(r)
        c.refresh_from_db();self.assertEqual(c.cierre,foto)

    def test_anular_dinero_ya_gastado_se_bloquea(self):
        r=self.recibir()
        from .test_operaciones import OperacionesTests
        s=OperacionesTests.solicitar(self,monto='15');OperacionesTests.aprobar(self,s)
        OperacionesTests.desembolsar(self,s)
        with self.assertRaises(ValidationError):self.anular(r)
        self.assertEqual(Ingreso.objects.get(pk=r.ingreso_id).estado,'REGISTRADO')

    def test_rollback_anulacion_conserva_aporte_y_cobertura(self):
        s=self.aprobar();r=self.pago_pad(s)
        a=aportes.pedir_anulacion(usuario=self.secretaria,recepcion_id=r.pk,clave=uuid.uuid4(),motivo='Ficticio')
        revision=aportes.anular(usuario=self.directora,anulacion_id=a.pk,decision='APROBADA')
        with patch.object(Obligacion,'actualizar_estado',side_effect=DatabaseError('Ficticio')),self.assertRaises(DatabaseError):
            aportes.anular(usuario=self.directora,anulacion_id=a.pk,decision='APROBADA',revision=revision,confirmar=True)
        self.assertEqual(Ingreso.objects.get().estado,'REGISTRADO');self.assertEqual(Donacion.objects.filter(estado='RECIBIDA').count(),6)
        self.assertEqual(AnulacionDonacion.objects.get(pk=a.pk).estado,'PENDIENTE')

    def test_portal_no_ignora_convenio_incumplido_ajeno(self):
        self.aprobar()
        ConvenioPago.objects.create(estudiante=self.estudiante,usuario_autoriza=self.directora,fecha_convenio=timezone.localdate(),monto_convenido=20,numero_cuotas=1,estado='INCUMPLIDO')
        self.assertFalse(solvente(self.estudiante))

    def test_cobertura_no_ignora_cuota_vencida_ajena(self):
        self.aprobar()
        c=ConvenioPago.objects.create(estudiante=self.estudiante,usuario_autoriza=self.directora,fecha_convenio=self.inicio,monto_convenido=20,numero_cuotas=1,estado='ACTIVO')
        CuotaConvenio.objects.create(convenio=c,numero_cuota=1,fecha_vencimiento=self.inicio,monto_cuota=20,estado='PENDIENTE')
        self.assertFalse(solvente(self.estudiante))

    def test_cobertura_restriccion_positiva_y_unica(self):
        s=self.aprobar();c=s.coberturas.first()
        with self.assertRaises(IntegrityError),transaction.atomic():CoberturaPadrinazgo.objects.create(solicitud=s,obligacion=c.obligacion,monto=1)
        with self.assertRaises(IntegrityError),transaction.atomic():CoberturaPadrinazgo.objects.filter(pk=c.pk).update(monto=0)

    def test_http_formularios_y_buscador_no_exigen_ids_manuales(self):
        self.assertContains(self.client.get(reverse('aportes_buscar'),{'q':self.estudiante.nombres}),'Preparar padrinazgo')
        datos={'clave':str(uuid.uuid4()),'donante':self.donante.pk,'inicio':str(self.inicio),'limite':str(self.limite),
            'modalidad':'PORCENTAJE','porcentaje':'100','observaciones':'Ficticio'}
        for pk in self.ids:datos[f'seleccionar_{pk}']='on'
        self.assertEqual(self.client.post(reverse('aportes_solicitar',args=[self.matricula.pk]),datos).status_code,302)
        s=SolicitudPadrinazgo.objects.get();self.client.force_login(self.directora);url=reverse('aportes_solicitud',args=[s.pk])
        r=self.client.post(url,{'decision':'APROBADA'});self.assertContains(r,'Confirmar autorización definitiva')
        self.assertEqual(self.client.post(url,{'decision':'APROBADA','revision':r.context['form'].data['revision'],'accion':'confirmar'}).status_code,302)

    def test_http_documento_privado_y_csrf(self):
        from .test_operaciones import OperacionesTests
        r=self.recibir(archivo=OperacionesTests.png(self))
        self.assertEqual(self.client.get(reverse('operaciones_documento',args=[r.comprobante_id])).status_code,200)
        c=Client(enforce_csrf_checks=True);c.force_login(self.secretaria)
        self.assertEqual(c.post(reverse('aportes_recibir_general'),{}).status_code,403)
        self.assertEqual(self.client.get('/media/'+r.comprobante.nombre).status_code,404)

    def test_migracion_solo_crea_tablas_nuevas(self):
        import importlib
        m=importlib.import_module('financiero.migrations.0005_donaciones_padrinazgos')
        permitidas={'coberturapadrinazgo','historialdonante','recepciondonacion','lineadonacion','solicitudpadrinazgo','revisionpadrinazgo','anulaciondonacion'}
        for op in m.Migration.operations:self.assertIn((getattr(op,'model_name',None) or getattr(op,'name','')).lower(),permitidas)

    def test_comprobante_conserva_nombre_y_descripcion_originales(self):
        r=self.recibir()
        self.crear_donante(donante_id=self.donante.pk,nombre_completo='Nombre actualizado')
        self.assertContains(self.client.get(reverse('aportes_recibo',args=[r.pk])),'Padrino PRIVADO')
        self.assertNotContains(self.client.get(reverse('aportes_recibo',args=[r.pk])),'Nombre actualizado')

    def test_comprobante_anonimo_no_publica_nombre_privado(self):
        self.crear_donante(donante_id=self.donante.pk,es_anonimo=True)
        r=self.recibir();respuesta=self.client.get(reverse('aportes_recibo',args=[r.pk]))
        self.assertContains(respuesta,'Donante anónimo');self.assertNotContains(respuesta,'Padrino PRIVADO')

    def test_solicitud_porcentaje_reenvio_tras_aprobar(self):
        clave=uuid.uuid4();s=self.solicitar(clave=clave,modalidad='PORCENTAJE',porcentaje='50');self.aprobar(s)
        self.assertEqual(self.solicitar(clave=clave,modalidad='PORCENTAJE',porcentaje='50').pk,s.pk)

    def test_fecha_obligacion_cambiada_invalida_solicitud(self):
        s=self.solicitar();Obligacion.objects.filter(pk=self.ids[0]).update(fecha_vencimiento=timezone.localdate()+timedelta(days=60))
        with self.assertRaises(ValidationError):self.aprobar(s)

    def test_orden_de_bloqueos_recepcion_compartido_con_caja(self):
        from django.db.models.query import QuerySet
        s=self.aprobar();orden=[];original=QuerySet.select_for_update
        def observar(q,*a,**k):orden.append(q.model.__name__);return original(q,*a,**k)
        with patch.object(QuerySet,'select_for_update',observar):self.pago_pad(s)
        self.assertEqual(orden[:9],['Usuario','Caja','Estudiante','Matricula','Obligacion','Donante','Padrinazgo','SolicitudPadrinazgo','CoberturaPadrinazgo'])

    def test_desactivar_donante_no_retira_cobertura(self):
        self.aprobar();self.crear_donante(donante_id=self.donante.pk,estado='INACTIVO')
        self.assertTrue(solvente(self.estudiante))

    def test_recepcion_no_financia_deuda_superior_al_compromiso(self):
        s=self.aprobar(self.solicitar(asignaciones=[(pk,Decimal('10')) for pk in self.ids]))
        with self.assertRaises(ValidationError):self.pago_pad(s)

    def test_reportes_vencidos_y_directorio_csv_protegido(self):
        s=self.aprobar();Padrinazgo.objects.filter(pk=s.padrinazgo_id).update(fecha_fin=timezone.localdate()-timedelta(days=1))
        self.assertEqual(self.client.get(reverse('aportes_panel'),{'directorio':'csv'}).status_code,403)
        self.client.force_login(self.directora)
        respuesta=self.client.get(reverse('aportes_reporte'),{'compromiso':'VENCIDO','cobertura':'TOTAL'})
        self.assertEqual(len(respuesta.context['compromisos']),1)
        self.assertEqual(self.client.get(reverse('aportes_panel'),{'directorio':'csv'}).status_code,200)

    def test_fecha_inicial_formulario_html5_se_muestra_en_iso(self):
        r=self.client.get(reverse('aportes_solicitar',args=[self.matricula.pk]))
        self.assertContains(r,f'value="{timezone.localdate().isoformat()}"')

    def test_revision_fecha_obligatoria_devuelve_formulario_sin_error_500(self):
        s=self.aprobar();self.client.force_login(self.directora)
        r=self.client.post(reverse('aportes_revision',args=[s.pk]),{'clave':str(uuid.uuid4()),'accion':'PRORROGA','motivo':'Solicitud de ampliación'})
        self.assertContains(r,'Indique la nueva fecha límite.')
        self.assertFalse(RevisionPadrinazgo.objects.exists())
        with self.assertRaises(ValidationError):self.revisar(s,limite=None)

    def test_solicitud_porcentaje_faltante_indica_campo(self):
        datos={'clave':str(uuid.uuid4()),'donante':self.donante.pk,'inicio':str(self.inicio),'limite':str(self.limite),'modalidad':'PORCENTAJE','observaciones':'Ficticia'}
        r=self.client.post(reverse('aportes_solicitar',args=[self.matricula.pk]),datos)
        self.assertContains(r,'Indique el porcentaje solicitado.')

    def test_http_recepcion_con_desglose_y_reenvio(self):
        s=self.aprobar();url=reverse('aportes_recibir',args=[self.matricula.pk])
        datos={'clave':str(uuid.uuid4()),'donante':self.donante.pk,'solicitud':s.pk,'modalidad':'PADRINAZGO',
            'monto':'10','metodo':'EFECTIVO','referencia':'HTTP-F6','fecha':self.fecha.isoformat(),f'aporte_{self.ids[0]}':'10'}
        for _ in range(2):self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(RecepcionDonacion.objects.count(),1);self.assertEqual(Ingreso.objects.get().monto,10)
        self.assertEqual(Donacion.objects.get().monto,10)

    def test_http_prorroga_conserva_accion_y_confirma_revision(self):
        s=self.aprobar();self.client.force_login(self.directora);url=reverse('aportes_revision',args=[s.pk])
        datos={'clave':str(uuid.uuid4()),'accion':'PRORROGA','paso':'comparar','motivo':'Amplía el plazo',
            'limite':str(self.limite+timedelta(days=60))}
        r=self.client.post(url,datos);self.assertContains(r,'Confirmar resolución definitiva')
        datos.update(paso='confirmar',revision=r.context['form'].data['revision'])
        self.assertEqual(self.client.post(url,datos).status_code,302)
        s.padrinazgo.refresh_from_db();self.assertEqual(s.padrinazgo.fecha_fin,self.limite+timedelta(days=60))

    def test_matricula_parcial_padrinazgo_exige_pago_completo_parte_estudiante(self):
        from .servicios import registrar_pago,reservar_recibo
        o=next(o for o in self.obligaciones if not o.concepto.permite_abonos)
        self.aprobar(self.solicitar(asignaciones=[(o.pk,Decimal('10'))]))
        datos=dict(usuario=self.secretaria,estudiante=self.estudiante,metodo='EFECTIVO',referencia='Parte estudiante')
        for monto in ('5','20'):
            with self.assertRaises(ValidationError):registrar_pago(**datos,token=reservar_recibo(self.secretaria,self.estudiante),aplicaciones=[(o.pk,Decimal(monto))])
        registrar_pago(**datos,token=reservar_recibo(self.secretaria,self.estudiante),aplicaciones=[(o.pk,Decimal('10'))])
        self.assertEqual(importes(o)[2],10);self.assertEqual(aportes.cubierta(o),10)

    def test_formulario_cobro_muestra_parte_estudiante_sin_exponer_donante(self):
        o=next(o for o in self.obligaciones if not o.concepto.permite_abonos)
        self.aprobar(self.solicitar(asignaciones=[(o.pk,Decimal('10'))]))
        r=self.client.get(reverse('finanzas_pago',args=[self.estudiante.pk]))
        self.assertContains(r,'a cargo del estudiante USD 10.00');self.assertNotContains(r,'Padrino PRIVADO')
