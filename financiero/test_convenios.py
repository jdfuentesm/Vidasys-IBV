"""Convenios completos y revisiones definidas; solo SQLite efímero y datos ficticios."""
import importlib
import uuid
from datetime import date,timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib import admin
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import DatabaseError,IntegrityError,transaction,connection
from django.test import TestCase,Client,RequestFactory
from django.urls import reverse
from django.utils import timezone
from academico.flujo import matricular
from academico.models import Estudiante
from core.models import Usuario
from . import convenios
from .models import (SolicitudConvenio,RevisionConvenio,ConvenioPago,ConvenioObligacion,CuotaConvenio,
                     AplicacionPagoCuota,Pago,DetallePago,Obligacion)
from .consultas import importes,solvente,cuenta
from .servicios import reservar_recibo,registrar_pago


class ConveniosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from academico.test_flujo import FlujoAcademicoTests
        FlujoAcademicoTests.setUpTestData.__func__(cls)
        cls.admin=Usuario.objects.create_user('conv-admin','conv-admin@example.test','ficticia',rol='ADMINISTRADOR',is_staff=True,is_superuser=True)

        # Nuevo requisito operativo: los cobros de regresión parten de una caja propia abierta.
        import uuid
        from .caja import abrir
        for operador in (cls.secretaria, cls.admin):
            abrir(usuario=operador, clave=uuid.uuid4(), fondo='0.00')

    def setUp(self):
        self.matricula=matricular(estudiante=self.estudiante,ciclo=self.ciclo,numero_matricula='CONV-1',fecha_matricula=date(2026,1,2))[0]
        self.originales=list(self.matricula.obligaciones.order_by('pk'))
        self.ids=[o.pk for o in self.originales]
        self.clave=uuid.uuid4()
        self.client.force_login(self.secretaria)

    def cuotas(self,total='120.00'):
        total=Decimal(total)
        return [{'fecha':str(timezone.localdate()),'monto':str(total/Decimal('4'))},
                {'fecha':str(timezone.localdate()+timedelta(days=20)),'monto':str(total*Decimal('3')/Decimal('4'))}]

    def solicitar(self,**cambios):
        return convenios.solicitar(**(dict(usuario=self.secretaria,estudiante_id=self.estudiante.pk,
            obligaciones=self.ids,cuotas=self.cuotas(),justificacion='Solicitud ficticia',clave=self.clave)|cambios))

    def autorizar(self,s=None,**cambios):
        s=s or self.solicitar()
        datos=dict(obligaciones=self.ids,cuotas=self.cuotas(),motivo='Resolución ficticia')|cambios
        _,revision=convenios.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        resultado=convenios.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=revision,**datos)
        return resultado.convenio

    def desglose_fixture(self,convenio,monto):
        # Datos de prueba explícitos; la aplicación no distribuye automáticamente.
        falta=Decimal(monto);filas=[]
        for o in Obligacion.objects.filter(convenios__convenio=convenio).order_by('pk'):
            aplicado=min(importes(o)[2],falta)
            if aplicado>0:filas.append((o.pk,aplicado));falta-=aplicado
        return filas

    def pagar(self,c,cuota,monto,**cambios):
        return convenios.registrar_abono(**(dict(usuario=self.secretaria,convenio_id=c.pk,
            token=reservar_recibo(self.secretaria,self.estudiante),metodo='EFECTIVO',referencia='Referencia ficticia',
            cuotas=[(cuota.pk,Decimal(monto))],obligaciones=self.desglose_fixture(c,monto))|cambios))

    def test_solicitar_no_modifica_saldos_solvencia_ni_pago(self):
        antes=list(Obligacion.objects.values());solvencia=solvente(self.estudiante)
        s=self.solicitar()
        self.assertEqual(self.solicitar().pk,s.pk)
        self.assertEqual(list(Obligacion.objects.values()),antes)
        self.assertEqual(solvente(self.estudiante),solvencia)
        self.assertFalse(ConvenioPago.objects.exists());self.assertFalse(Pago.objects.exists())
        with self.assertRaises(ValidationError):self.solicitar(justificacion='Otro motivo')
        with self.assertRaises(ValidationError):self.solicitar(clave=uuid.uuid4())

    def test_aprobar_cuotas_distintas_y_no_duplica_deuda(self):
        antes=list(Obligacion.objects.values())
        c=self.autorizar()
        self.assertEqual(c.estado,'ACTIVO');self.assertEqual(c.monto_convenido,Decimal('120'))
        self.assertEqual(list(c.cuotas.order_by('numero_cuota').values_list('monto_cuota',flat=True)),[Decimal('30'),Decimal('90')])
        self.assertEqual(c.obligaciones_incluidas.count(),6)
        self.assertEqual(list(Obligacion.objects.values()),antes)
        self.assertEqual(cuenta(self.estudiante)['saldo_total'],Decimal('120'))
        self.assertTrue(solvente(self.estudiante))
        self.assertFalse(Pago.objects.exists())

    def test_suma_exacta_sin_intereses_y_precision(self):
        for filas in [[{'fecha':str(timezone.localdate()),'monto':'119.99'}],
                      [{'fecha':str(timezone.localdate()),'monto':'120.01'}],
                      [{'fecha':str(timezone.localdate()),'monto':'120.001'}],
                      [{'fecha':str(timezone.localdate()),'monto':'NaN'}],
                      [{'fecha':str(timezone.localdate()-timedelta(days=1)),'monto':'120'}]]:
            with self.assertRaises(ValidationError):self.solicitar(cuotas=filas)
        self.assertFalse(SolicitudConvenio.objects.exists())

    def test_obligaciones_no_vencidas_y_vencidas_autorizadas(self):
        Obligacion.objects.filter(pk=self.ids[0]).update(fecha_vencimiento=timezone.localdate()+timedelta(days=10))
        c=self.autorizar()
        self.assertEqual(c.obligaciones_incluidas.count(),6)

    def test_descuentos_y_pagos_previos_se_conservan(self):
        from . import becas
        s=becas.solicitar(usuario=self.secretaria,matricula_id=self.matricula.pk,porcentaje='50',conceptos=['MATRICULA'],alcance='AMBAS',justificacion='Beca',clave=uuid.uuid4())
        datos=dict(porcentaje='50',conceptos=['MATRICULA'],alcance='AMBAS',obligaciones=[self.ids[0]],observaciones='Beca')
        _,token=becas.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**datos)
        mensual=self.originales[1]
        registrar_pago(usuario=self.secretaria,estudiante=self.estudiante,token=reservar_recibo(self.secretaria,self.estudiante),metodo='EFECTIVO',referencia='',aplicaciones=[(mensual.pk,Decimal('5'))])
        pagos=list(Pago.objects.values());detalles=list(DetallePago.objects.values())
        solicitud=self.solicitar(cuotas=self.cuotas('105'))
        c=self.autorizar(solicitud,cuotas=self.cuotas('105'))
        self.assertEqual(c.monto_convenido,Decimal('105'))
        self.assertEqual(list(Pago.objects.values()),pagos);self.assertEqual(list(DetallePago.objects.values()),detalles)

    def test_rechazo_y_permisos(self):
        s=self.solicitar()
        with self.assertRaises(ValidationError):convenios.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA')
        for actor in [self.admin,self.secretaria,self.docente]:
            with self.assertRaises(PermissionDenied):convenios.resolver(usuario=actor,solicitud_id=s.pk,decision='RECHAZADA',motivo='No')
        convenios.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',motivo='No procede')
        self.assertFalse(ConvenioPago.objects.exists())
        s.refresh_from_db()
        with self.assertRaises(ValidationError):s.save()
        with self.assertRaises(ValidationError):s.delete()

    def test_aprobacion_idempotente_y_cambios_obsoletos(self):
        s=self.solicitar();datos=dict(obligaciones=self.ids,cuotas=self.cuotas(),motivo='Aprobación')
        _,revision=convenios.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        primero=convenios.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=revision,**datos)
        segundo=convenios.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=revision,**datos)
        self.assertEqual(primero.fecha_resolucion,segundo.fecha_resolucion)
        self.assertEqual(ConvenioPago.objects.count(),1)
        with self.assertRaises(ValidationError):convenios.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',motivo='Cambio')

    def test_saldo_cambia_tras_previsualizar_no_autoriza(self):
        s=self.solicitar();datos=dict(obligaciones=self.ids,cuotas=self.cuotas(),motivo='Aprobación')
        _,revision=convenios.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        Obligacion.objects.filter(pk=self.ids[0]).update(descripcion='Cambio posterior')
        with self.assertRaisesMessage(ValidationError,'cambiaron'):convenios.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=revision,**datos)
        self.assertFalse(ConvenioPago.objects.exists())

    def test_obligaciones_duplicadas_o_ajenas_no_admitidas(self):
        with self.assertRaises(ValidationError):self.solicitar(obligaciones=[self.ids[0],self.ids[0]])
        with self.assertRaises(ValidationError):self.solicitar(obligaciones=[999999])
        c=self.autorizar()
        with self.assertRaises(ValidationError):self.solicitar(clave=uuid.uuid4())
        self.assertEqual(c.obligaciones_incluidas.count(),6)

    def test_abonos_y_cumplimiento_sin_doble_contabilizacion(self):
        c=self.autorizar();q1,q2=list(c.cuotas.order_by('numero_cuota'))
        self.pagar(c,q1,'5')
        self.assertEqual(convenios.resumen(c)['saldo'],Decimal('115'))
        self.assertEqual(cuenta(self.estudiante)['saldo_total'],Decimal('115'))
        self.pagar(c,q1,'25')
        self.pagar(c,q2,'90')
        c.refresh_from_db();self.assertEqual(c.estado,'CUMPLIDO')
        self.assertEqual(convenios.resumen(c)['saldo'],Decimal('0'))
        self.assertTrue(solvente(self.estudiante))
        self.assertEqual(sum(Pago.objects.values_list('monto_total',flat=True)),Decimal('120'))
        self.assertTrue(all(o.estado=='PAGADA' for o in Obligacion.objects.all()))
        self.assertEqual(sum(DetallePago.objects.values_list('monto_aplicado',flat=True)),Decimal('120'))
        self.assertEqual(sum(AplicacionPagoCuota.objects.values_list('monto_aplicado',flat=True)),Decimal('120'))

    def test_pago_idempotente_y_recibo_inmutable(self):
        c=self.autorizar();q=c.cuotas.first();token=reservar_recibo(self.secretaria,self.estudiante)
        pago,creado=self.pagar(c,q,'5',token=token)
        antes=Pago.objects.values().get(pk=pago.pk)
        repetido,creado2=self.pagar(c,q,'5',token=token,obligaciones=[(self.ids[0],Decimal('5'))])
        self.assertTrue(creado);self.assertFalse(creado2);self.assertEqual(pago.pk,repetido.pk)
        self.assertEqual(Pago.objects.values().get(pk=pago.pk),antes)
        with self.assertRaises(ValidationError):self.pagar(c,q,'4',token=token)
        self.assertEqual(Pago.objects.count(),1)

    def test_desglose_obligatorio_limites_y_cuotas_ajenas(self):
        c=self.autorizar();q=c.cuotas.first()
        for cambios in [{'obligaciones':[]},{'obligaciones':[(self.ids[0],Decimal('4'))]},
                {'cuotas':[(999999,Decimal('5'))]}, {'obligaciones':[(999999,Decimal('5'))]},
                {'cuotas':[(q.pk,Decimal('31'))],'obligaciones':[(self.ids[0],Decimal('20')),(self.ids[1],Decimal('11'))]},
                {'obligaciones':[(self.ids[0],Decimal('5')),(self.ids[0],Decimal('5'))]}]:
            with self.assertRaises(ValidationError):self.pagar(c,q,'5',**cambios)
        self.assertFalse(Pago.objects.exists())

    def test_cobro_ordinario_no_elude_convenio(self):
        c=self.autorizar()
        for estado in ['ACTIVO','CUMPLIDO','INCUMPLIDO']:
            ConvenioPago.objects.filter(pk=c.pk).update(estado=estado)
            with self.assertRaises(ValidationError):registrar_pago(usuario=self.secretaria,estudiante=self.estudiante,
                token=reservar_recibo(self.secretaria,self.estudiante),metodo='EFECTIVO',referencia='',aplicaciones=[(self.ids[0],Decimal('20'))])

    def test_cuota_vencida_insolvente_sin_otros_cambios(self):
        c=self.autorizar();self.assertTrue(solvente(self.estudiante))
        CuotaConvenio.objects.filter(convenio=c,numero_cuota=1).update(fecha_vencimiento=timezone.localdate()-timedelta(days=1))
        self.assertFalse(solvente(self.estudiante))
        self.assertEqual(convenios.resumen(c)['vencidas'],1)

    def test_otras_deudas_mantienen_insolvencia(self):
        ids=[self.ids[0]]
        s=self.solicitar(obligaciones=ids,cuotas=self.cuotas('20'))
        self.autorizar(s,obligaciones=ids,cuotas=self.cuotas('20'))
        self.assertFalse(solvente(self.estudiante))

    def test_rollback_al_crear_cuotas_y_al_resolver(self):
        s=self.solicitar();antes=list(Obligacion.objects.values())
        for modelo in [CuotaConvenio,SolicitudConvenio]:
            with patch.object(modelo,'save',side_effect=DatabaseError('Fallo ficticio')):
                with self.assertRaises(DatabaseError):self.autorizar(s)
            self.assertFalse(ConvenioPago.objects.exists());self.assertFalse(ConvenioObligacion.objects.exists())
            self.assertEqual(list(Obligacion.objects.values()),antes)

    def test_rollback_cobro_en_aplicaciones_conserva_saldos(self):
        c=self.autorizar();q=c.cuotas.first()
        antes=list(Obligacion.objects.values())
        with patch.object(AplicacionPagoCuota,'save',side_effect=DatabaseError('Fallo ficticio')):
            with self.assertRaises(DatabaseError):self.pagar(c,q,'5')
        self.assertFalse(Pago.objects.exists());self.assertFalse(DetallePago.objects.exists())
        self.assertEqual(list(Obligacion.objects.values()),antes)

    def test_cancelar_sin_pagos_preserva_historial_y_reactiva_solvencia_original(self):
        c=self.autorizar();clave=uuid.uuid4();datos=dict(usuario=self.directora,convenio_id=c.pk,accion='CANCELACION',motivo='Justificación',clave=clave)
        antes=list(Obligacion.objects.values());cuotas=list(c.cuotas.values())
        previo=convenios.revisar(**datos)
        r=convenios.revisar(**datos,confirmar=True,revision=previo['revision'])
        c.refresh_from_db();self.assertEqual(c.estado,'CANCELADO')
        self.assertFalse(solvente(self.estudiante))
        self.assertEqual(list(Obligacion.objects.values()),antes);self.assertEqual(list(c.cuotas.values()),cuotas)
        self.assertEqual(convenios.revisar(**datos,confirmar=True,revision=previo['revision']).pk,r.pk)
        with self.assertRaises(ValidationError):r.save()

    def test_modificar_sin_pagos_crea_version_sin_borrar_original(self):
        c=self.autorizar();datos=dict(usuario=self.directora,convenio_id=c.pk,accion='MODIFICACION',motivo='Nuevas condiciones',clave=uuid.uuid4(),
            obligaciones=self.ids,cuotas=[{'fecha':str(timezone.localdate()+timedelta(days=30)),'monto':'120'}])
        antes=convenios.revisar(**datos)
        r=convenios.revisar(**datos,confirmar=True,revision=antes['revision'])
        c.refresh_from_db();self.assertEqual(c.estado,'CANCELADO')
        self.assertEqual(r.nuevo.estado,'ACTIVO');self.assertEqual(r.nuevo.cuotas.count(),1)
        self.assertEqual(c.cuotas.count(),2)
        self.assertEqual(cuenta(self.estudiante)['saldo_total'],Decimal('120'))
        self.assertTrue(solvente(self.estudiante))

    def test_revision_con_pagos_bloqueada(self):
        c=self.autorizar();self.pagar(c,c.cuotas.first(),'5')
        for accion in ['CANCELACION','MODIFICACION']:
            with self.assertRaisesMessage(ValidationError,'movimientos de pago'):
                convenios.revisar(usuario=self.directora,convenio_id=c.pk,accion=accion,motivo='Cambiar',clave=uuid.uuid4(),obligaciones=self.ids,cuotas=self.cuotas('115'))
        self.assertEqual(Pago.objects.count(),1);self.assertFalse(RevisionConvenio.objects.exists())

    def test_permisos_cobros_y_admin(self):
        c=self.autorizar();q=c.cuotas.first()
        with self.assertRaises(PermissionDenied):self.pagar(c,q,'5',usuario=self.directora)
        req=RequestFactory().get('/admin/');req.user=self.admin
        for modelo in [ConvenioPago,AplicacionPagoCuota]:
            configuracion=admin.site._registry[modelo]
            self.assertFalse(configuracion.has_add_permission(req));self.assertFalse(configuracion.has_change_permission(req));self.assertFalse(configuracion.has_delete_permission(req))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post('/admin/financiero/conveniopago/add/',{}).status_code,403)

    def test_portal_solo_convenios_propios(self):
        c=self.autorizar()
        u=Usuario.objects.create_user('conv-est','conv-est@example.test','ficticia',rol='ESTUDIANTE')
        self.estudiante.usuario=u;self.estudiante.save(update_fields=['usuario'])
        self.client.force_login(u)
        self.assertContains(self.client.get(reverse('convenios_portal',args=[c.pk])),'Convenio #')
        otro=Estudiante.objects.create(codigo_estudiante='CONV-OTRO',nombres='Otro',apellidos='Ficticio',fecha_ingreso=date(2026,1,1),estado='ACTIVO')
        otro_c=ConvenioPago.objects.create(estudiante=otro,usuario_autoriza=self.directora,fecha_convenio=timezone.localdate(),monto_convenido='1',numero_cuotas=1,estado='ACTIVO')
        self.assertEqual(self.client.get(reverse('convenios_portal',args=[otro_c.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('convenios_detalle',args=[c.pk])).status_code,403)

    def test_migracion_solo_dos_tablas_nuevas(self):
        m=importlib.import_module('financiero.migrations.0002_convenios_institucionales').Migration
        self.assertEqual({op.name for op in m.operations},{'RevisionConvenio','SolicitudConvenio'})
        self.assertTrue(all(type(op).__name__=='CreateModel' for op in m.operations))
        self.assertIn('solicitud_convenio',connection.introspection.table_names())
        self.assertIn('revision_convenio',connection.introspection.table_names())

    def datos_formset(self,cuotas):
        datos={'cuotas-TOTAL_FORMS':str(len(cuotas)),'cuotas-INITIAL_FORMS':'0','cuotas-MIN_NUM_FORMS':'1','cuotas-MAX_NUM_FORMS':'100'}
        for i,c in enumerate(cuotas):
            datos[f'cuotas-{i}-fecha']=c['fecha'];datos[f'cuotas-{i}-monto']=c['monto']
        return datos

    def test_http_solicitud_autorizacion_abono_recibo_y_reenvio(self):
        url=reverse('convenios_nuevo')+f'?estudiante={self.estudiante.pk}&cantidad=2'
        self.assertContains(self.client.get(url),'Cuota 2')
        datos={'clave':self.clave,'obligaciones':self.ids,'motivo':'Solicitud HTTP',**self.datos_formset(self.cuotas())}
        self.assertEqual(self.client.post(url,datos).status_code,302)
        s=SolicitudConvenio.objects.get();url=reverse('convenios_solicitud',args=[s.pk])
        self.assertEqual(self.client.post(url,{}).status_code,403)
        self.client.force_login(self.directora)
        datos=dict(datos,decision='APROBADA',motivo='Autorización HTTP',accion='comparar')
        response=self.client.post(url,datos)
        self.assertContains(response,'Comparación financiera')
        datos['revision']=response.context['form'].data['revision'];datos['accion']='resolver'
        self.assertEqual(self.client.post(url,datos).status_code,302)
        s.refresh_from_db();c=s.convenio;q=c.cuotas.first()
        self.client.force_login(self.admin)
        url=reverse('convenios_cobro',args=[c.pk])
        response=self.client.get(url)
        token=response.context['form'].initial['token']
        datos={'token':token,'metodo':'TRANSFERENCIA','referencia':'REF-FICTICIA',f'cuota_{q.pk}':'5',f'obligacion_{self.ids[0]}':'5'}
        response=self.client.post(url,datos)
        self.assertEqual(response.status_code,302)
        self.assertContains(self.client.get(response.url),'Aplicación a cuotas')
        self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(Pago.objects.count(),1)

    def test_direccion_ajusta_cantidad_de_cuotas_desde_interfaz(self):
        s=self.solicitar();self.client.force_login(self.directora)
        url=reverse('convenios_solicitud',args=[s.pk])+'?cantidad=3'
        self.assertContains(self.client.get(url),'Cuota 3')
        filas=[{'fecha':str(timezone.localdate()+timedelta(days=n)),'monto':str(m)} for n,m in [(1,20),(2,40),(3,60)]]
        datos={'clave':uuid.uuid4(),'decision':'APROBADA','motivo':'Tres cuotas','obligaciones':self.ids,'accion':'comparar',**self.datos_formset(filas)}
        response=self.client.post(url,datos)
        self.assertContains(response,'Comparación financiera')
        datos['revision']=response.context['form'].data['revision'];datos['accion']='resolver'
        self.assertEqual(self.client.post(url,datos).status_code,302)
        s.refresh_from_db();self.assertEqual(s.convenio.cuotas.count(),3)

    def test_http_revision_cancela_y_rechaza_roles_no_autorizados(self):
        c=self.autorizar();url=reverse('convenios_revision',args=[c.pk])
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.admin);self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.directora)
        datos={'clave':uuid.uuid4(),'accion':'comparar','tipo_revision':'CANCELACION','motivo':'Cancelación HTTP'}
        response=self.client.post(url,datos)
        self.assertContains(response,'Autorizar revisión')
        datos['revision']=response.context['form'].data['revision'];datos['accion']='resolver'
        self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(self.client.post(url,datos).status_code,302)
        c.refresh_from_db();self.assertEqual(c.estado,'CANCELADO')

    def test_rol_cambia_y_csrf_se_revalidan(self):
        s=self.solicitar();datos=dict(obligaciones=self.ids,cuotas=self.cuotas(),motivo='Autorización')
        _,token=convenios.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        Usuario.objects.filter(pk=self.directora.pk).update(rol='ADMINISTRADOR',is_superuser=True)
        with self.assertRaises(PermissionDenied):convenios.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**datos)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.secretaria)
        self.assertEqual(csrf.post(reverse('convenios_nuevo')+f'?estudiante={self.estudiante.pk}&cantidad=2',{}).status_code,403)
        self.client.logout();self.assertEqual(self.client.get(reverse('convenios_listado')).status_code,302)

    def test_modificacion_rollback_conserva_convenio_anterior(self):
        c=self.autorizar();datos=dict(usuario=self.directora,convenio_id=c.pk,accion='MODIFICACION',motivo='Revisión',clave=uuid.uuid4(),obligaciones=self.ids,cuotas=self.cuotas())
        previo=convenios.revisar(**datos)
        with patch.object(RevisionConvenio,'save',side_effect=DatabaseError('Fallo ficticio')):
            with self.assertRaises(DatabaseError):convenios.revisar(**datos,confirmar=True,revision=previo['revision'])
        c.refresh_from_db();self.assertEqual(c.estado,'ACTIVO')
        self.assertEqual(ConvenioPago.objects.count(),1)
        self.assertEqual(c.cuotas.count(),2)

    def test_donacion_posterior_no_se_redistribuye_silenciosamente(self):
        from .models import Donante,Donacion
        c=self.autorizar()
        donante=Donante.objects.create(nombre_completo='Donante ficticio',tipo='PERSONA',es_anonimo=True,estado='ACTIVO',fecha_registro=timezone.now(),fecha_actualizacion=timezone.now())
        Donacion.objects.create(donante=donante,obligacion=self.originales[0],usuario_registra=self.secretaria,fecha_compromiso=timezone.localdate(),fecha_registro=timezone.now(),fecha_actualizacion=timezone.now(),monto='1',estado='RECIBIDA')
        with self.assertRaisesMessage(ValidationError,'no coinciden'):self.pagar(c,c.cuotas.first(),'5')
        self.assertFalse(Pago.objects.exists())

    def test_reportes_no_suman_cuotas_y_originales_como_dos_deudas(self):
        from reportes.consultas import generar
        c=self.autorizar();self.pagar(c,c.cuotas.first(),'5')
        datos=generar('resumen',self.admin,{})
        self.assertEqual(datos['filas'][0][1],'USD 5.00')
        self.assertEqual(datos['filas'][1][1],'USD 115.00')

    def test_todos_los_roles_respetan_solicitudes_decisiones_y_cobros(self):
        s=self.solicitar();c=self.autorizar(s)
        for rol in ['MAESTRO','PASTOR_PRINCIPAL','ESTUDIANTE']:
            u=Usuario.objects.create_user('c3-'+rol,rol+'@example.test','ficticia',rol=rol)
            self.client.force_login(u)
            for url in [reverse('convenios_listado'),reverse('convenios_solicitud',args=[s.pk]),reverse('convenios_detalle',args=[c.pk]),reverse('convenios_cobro',args=[c.pk])]:
                self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.directora)
        self.assertEqual(self.client.get(reverse('convenios_cobro',args=[c.pk])).status_code,403)
        self.assertEqual(self.client.get(reverse('convenios_nuevo')).status_code,403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('convenios_listado')).status_code,200)
        self.assertEqual(self.client.post(reverse('convenios_solicitud',args=[s.pk]),{}).status_code,403)

    def test_solicitud_inmutable_y_motivos_obligatorios(self):
        with self.assertRaises(ValidationError):self.solicitar(justificacion=' ')
        s=self.solicitar();s.justificacion='Cambiar'
        with self.assertRaises(ValidationError):s.save()
        with self.assertRaises(ValidationError):s.delete()
        c=self.autorizar()
        with self.assertRaises(ValidationError):convenios.revisar(usuario=self.directora,convenio_id=c.pk,accion='CANCELACION',motivo='',clave=uuid.uuid4())

    def test_recibo_previo_ordinario_y_de_convenio_comparten_numeracion(self):
        previo=registrar_pago(usuario=self.secretaria,estudiante=self.estudiante,token=reservar_recibo(self.secretaria,self.estudiante),metodo='EFECTIVO',referencia='Previo',aplicaciones=[(self.ids[1],Decimal('5'))])[0]
        snapshot=Pago.objects.values().get(pk=previo.pk)
        s=self.solicitar(cuotas=self.cuotas('115'));c=self.autorizar(s,cuotas=self.cuotas('115'))
        nuevo,_=self.pagar(c,c.cuotas.first(),'5')
        self.assertGreater(nuevo.pk,previo.pk)
        self.assertNotEqual(nuevo.numero_recibo,previo.numero_recibo)
        self.assertEqual(Pago.objects.values().get(pk=previo.pk),snapshot)

    def test_formato_fecha_iso_y_redistribucion_revision_visible(self):
        c=self.autorizar();self.client.force_login(self.directora)
        response=self.client.get(reverse('convenios_revision',args=[c.pk])+'?cantidad=3')
        self.assertContains(response,f'value="{timezone.localdate()}"')
        self.assertContains(response,'Cuota 3')

    def test_rechazo_http_no_exige_cuotas_nuevas(self):
        s=self.solicitar();self.client.force_login(self.directora)
        datos={'clave':uuid.uuid4(),'decision':'RECHAZADA','motivo':'Rechazo justificado','accion':'comparar'}
        response=self.client.post(reverse('convenios_solicitud',args=[s.pk]),datos)
        self.assertEqual(response.status_code,302)
        s.refresh_from_db();self.assertEqual(s.estado,'RECHAZADA')
        self.assertFalse(ConvenioPago.objects.exists())

    def test_pago_rechaza_usuario_reserva_ajena_y_monto_no_decimal(self):
        c=self.autorizar();q=c.cuotas.first()
        token=reservar_recibo(self.admin,self.estudiante)
        with self.assertRaises(ValidationError):self.pagar(c,q,'5',token=token)
        for valor in [Decimal('-1'),Decimal('NaN'),Decimal('0'),Decimal('1.001'),'5']:
            with self.subTest(valor=valor),self.assertRaises(ValidationError):self.pagar(c,q,'5',cuotas=[(q.pk,valor)])
        self.assertFalse(Pago.objects.exists())

    def test_incidencia_incumplido_formal_solo_se_regulariza_totalmente_al_cumplir(self):
        c=self.autorizar();ConvenioPago.objects.filter(pk=c.pk).update(estado='INCUMPLIDO')
        self.pagar(c,c.cuotas.first(),'30')
        c.refresh_from_db();self.assertEqual(c.estado,'INCUMPLIDO');self.assertFalse(solvente(self.estudiante))
        self.pagar(c,c.cuotas.order_by('numero_cuota').last(),'90')
        c.refresh_from_db();self.assertEqual(c.estado,'CUMPLIDO');self.assertTrue(solvente(self.estudiante))
