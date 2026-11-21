"""Becas institucionales: SQLite en memoria, datos ficticios y regresión de cobros."""
import importlib
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, transaction, connection
from django.db.models.query import QuerySet
from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from academico.flujo import matricular
from academico.models import Estudiante, Matricula
from core.models import Usuario
from . import becas
from .consultas import importes, solvente
from .models import (Beca, AplicacionBeca, SolicitudBeca, Obligacion, Pago, DetallePago,
                     ConvenioPago, ConvenioObligacion, Donante, Donacion)
from .servicios import registrar_pago, reservar_recibo


class BecasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from academico.test_flujo import FlujoAcademicoTests
        FlujoAcademicoTests.setUpTestData.__func__(cls)
        cls.admin=Usuario.objects.create_user('becas-admin','becas-admin@example.test','ficticia',
            rol='ADMINISTRADOR',is_staff=True,is_superuser=True)

        # Nuevo requisito operativo: los cobros de regresión parten de una caja propia abierta.
        import uuid
        from .caja import abrir
        for operador in (cls.secretaria, cls.admin):
            abrir(usuario=operador, clave=uuid.uuid4(), fondo='0.00')

    def setUp(self):
        self.matricula=matricular(estudiante=self.estudiante,ciclo=self.ciclo,numero_matricula='BECA-1',fecha_matricula=date(2026,1,2))[0]
        self.obligaciones=list(self.matricula.obligaciones.select_related('concepto').order_by('pk'))
        self.cargo=next(o for o in self.obligaciones if o.concepto.nombre=='MENSUALIDAD')
        self.clave=uuid.uuid4()
        self.client.force_login(self.secretaria)

    def solicitar(self,**kwargs):
        return becas.solicitar(**(dict(usuario=self.secretaria,matricula_id=self.matricula.pk,porcentaje='50',
            conceptos=['MATRICULA','MENSUALIDAD'],alcance='AMBAS',justificacion='Solicitud ficticia',clave=self.clave)|kwargs))

    def datos(self,**kwargs):
        return dict(porcentaje='50',conceptos=['MATRICULA','MENSUALIDAD'],alcance='AMBAS',
            obligaciones=[o.pk for o in self.obligaciones],observaciones='Resolución ficticia')|kwargs

    def aprobar(self,s,**kwargs):
        datos=self.datos(**kwargs)
        _,token=becas.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        return becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**datos)

    def pagar(self,o,monto):
        return registrar_pago(usuario=self.secretaria,estudiante=self.estudiante,
            token=reservar_recibo(self.secretaria,self.estudiante),metodo='EFECTIVO',referencia='',
            aplicaciones=[(o.pk,Decimal(monto))])[0]

    def test_solicitud_no_modifica_obligaciones_y_es_idempotente(self):
        antes=list(Obligacion.objects.values())
        s=self.solicitar()
        self.assertEqual(self.solicitar().pk,s.pk)
        self.assertEqual(list(Obligacion.objects.values()),antes)
        self.assertFalse(Beca.objects.exists())
        with self.assertRaises(ValidationError):self.solicitar(porcentaje='100')
        with self.assertRaises(ValidationError):self.solicitar(clave=uuid.uuid4())

    def test_cincuenta_por_ciento_matricula_y_mensualidades(self):
        s=self.aprobar(self.solicitar())
        self.assertEqual(s.estado,'APROBADA')
        self.assertEqual(Beca.objects.count(),1)
        self.assertEqual(AplicacionBeca.objects.count(),6)
        for o in Obligacion.objects.all():
            self.assertEqual(o.monto_descuento,Decimal('10'))
            self.assertEqual(importes(o)[2],Decimal('10'))
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(solvente(self.estudiante))
        self.assertEqual(s.directora_id,self.directora.pk)

    def test_cien_por_ciento_salda_sin_recibo_y_solventa(self):
        self.aprobar(self.solicitar(porcentaje='100'),porcentaje='100')
        for o in Obligacion.objects.all():
            self.assertEqual(o.estado,'PAGADA')
            self.assertEqual(importes(o)[2],Decimal('0'))
        self.assertTrue(solvente(self.estudiante))
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(DetallePago.objects.exists())

    def test_directora_puede_ajustar_porcentaje_conceptos_y_destinos(self):
        s=self.solicitar(conceptos=['MATRICULA'],alcance='NO_VENCIDAS')
        self.aprobar(s,porcentaje='100',conceptos=['MENSUALIDAD'],alcance='VENCIDAS',obligaciones=[self.cargo.pk])
        s.refresh_from_db();self.cargo.refresh_from_db()
        self.assertEqual(s.porcentaje_solicitado,Decimal('50'))
        self.assertEqual(s.resolucion['porcentaje'],'100')
        self.assertEqual(self.cargo.monto_descuento,Decimal('20'))
        self.assertEqual(AplicacionBeca.objects.count(),1)

    def test_retroactividad_y_vencimiento_hoy_no_es_vencida(self):
        hoy=timezone.localdate()
        Obligacion.objects.filter(pk=self.cargo.pk).update(fecha_vencimiento=hoy)
        self.cargo.refresh_from_db()
        s=self.solicitar()
        with self.assertRaises(ValidationError):self.aprobar(s,alcance='VENCIDAS',obligaciones=[self.cargo.pk])
        self.aprobar(s,alcance='NO_VENCIDAS',obligaciones=[self.cargo.pk])

    def test_no_retroactiva_no_beneficia_cargo_vencido(self):
        s=self.solicitar()
        with self.assertRaises(ValidationError):self.aprobar(s,alcance='NO_VENCIDAS',obligaciones=[self.cargo.pk])
        Obligacion.objects.filter(pk=self.cargo.pk).update(fecha_vencimiento=timezone.localdate()+timedelta(days=1))
        self.aprobar(s,alcance='NO_VENCIDAS',obligaciones=[self.cargo.pk])

    def test_pago_previo_compatible_conserva_recibo_y_donacion(self):
        pago=self.pagar(self.cargo,'5')
        donante=Donante.objects.create(nombre_completo='Donante ficticio',tipo='PERSONA',es_anonimo=True,estado='ACTIVO',fecha_registro=timezone.now(),fecha_actualizacion=timezone.now())
        Donacion.objects.create(donante=donante,obligacion=self.cargo,usuario_registra=self.secretaria,
            fecha_compromiso=date(2026,1,1),fecha_registro=timezone.now(),fecha_actualizacion=timezone.now(),monto='2',estado='RECIBIDA')
        antes=(list(Pago.objects.values()),list(DetallePago.objects.values()),list(Donacion.objects.values()))
        self.aprobar(self.solicitar(),obligaciones=[self.cargo.pk])
        self.cargo.refresh_from_db()
        self.assertEqual(importes(self.cargo)[2],Decimal('3'))
        self.assertEqual((list(Pago.objects.values()),list(DetallePago.objects.values()),list(Donacion.objects.values())),antes)
        self.assertTrue(Pago.objects.get(pk=pago.pk).observaciones.startswith('VIDASYS_RECIBO_V1'))

    def test_descuento_superior_saldo_bloquea_toda_aprobacion(self):
        self.pagar(self.cargo,'15')
        s=self.solicitar()
        with self.assertRaisesMessage(ValidationError,'supera saldo'):self.aprobar(s)
        self.assertFalse(Beca.objects.exists());self.assertFalse(AplicacionBeca.objects.exists())
        self.assertFalse(Obligacion.objects.exclude(monto_descuento=0).exists())
        s.refresh_from_db();self.assertEqual(s.estado,'PENDIENTE')

    def test_matricula_beca_parcial_exige_pago_completo_neto(self):
        o=next(o for o in self.obligaciones if o.concepto.nombre=='MATRICULA')
        self.assertFalse(o.concepto.permite_abonos)
        self.aprobar(self.solicitar(),conceptos=['MATRICULA'],obligaciones=[o.pk])
        with self.assertRaises(ValidationError):self.pagar(o,'5')
        pago=self.pagar(o,'10')
        self.assertEqual(pago.monto_total,Decimal('10'))
        o.refresh_from_db();self.assertEqual(o.estado,'PAGADA')
        self.assertEqual(importes(o)[2],Decimal('0'))

    def test_rechazo_exige_motivo_y_no_aplica_descuentos(self):
        s=self.solicitar()
        with self.assertRaises(ValidationError):becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA')
        becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',observaciones='No procede')
        self.assertFalse(Beca.objects.exists())
        self.assertFalse(Obligacion.objects.exclude(monto_descuento=0).exists())

    def test_permisos_servidor_incluso_superusuario_tecnico(self):
        s=self.solicitar()
        for actor in [self.secretaria,self.admin,self.docente]:
            with self.assertRaises(PermissionDenied):becas.previsualizar(usuario=actor,solicitud_id=s.pk,**self.datos())
            with self.assertRaises(PermissionDenied):becas.resolver(usuario=actor,solicitud_id=s.pk,decision='RECHAZADA',observaciones='No')
        for rol in ['PASTOR_PRINCIPAL','ESTUDIANTE']:
            actor=Usuario.objects.create_user('beca-'+rol,rol+'@example.test','ficticia',rol=rol)
            with self.assertRaises(PermissionDenied):becas.resolver(usuario=actor,solicitud_id=s.pk,decision='RECHAZADA',observaciones='No')
        for actor in [self.directora,self.admin,self.docente]:
            with self.assertRaises(PermissionDenied):self.solicitar(usuario=actor,clave=uuid.uuid4())

    def test_rol_e_inactividad_se_revalidan_al_resolver(self):
        s=self.solicitar();_,token=becas.previsualizar(usuario=self.directora,solicitud_id=s.pk,**self.datos())
        for cambio in [{'rol':'ADMINISTRADOR'},{'rol':'DIRECTORA','estado_cuenta':'BLOQUEADA'}]:
            Usuario.objects.filter(pk=self.directora.pk).update(**cambio)
            with self.assertRaises(PermissionDenied):becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**self.datos())
        self.assertFalse(Beca.objects.exists())

    def test_reintento_aprobacion_y_decision_contradictoria(self):
        s=self.solicitar();datos=self.datos()
        _,token=becas.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        primero=becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**datos)
        segundo=becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**datos)
        self.assertEqual(primero.fecha_resolucion,segundo.fecha_resolucion)
        self.assertEqual(Beca.objects.count(),1);self.assertEqual(AplicacionBeca.objects.count(),6)
        with self.assertRaises(ValidationError):becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',observaciones='Cambio')
        with self.assertRaises(ValidationError):becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**self.datos(porcentaje='100'))

    def test_previsualizacion_obsoleta_por_pago_no_aplica(self):
        s=self.solicitar();datos=self.datos(obligaciones=[self.cargo.pk])
        _,token=becas.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        self.pagar(self.cargo,'1')
        with self.assertRaisesMessage(ValidationError,'cambiaron'):becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**datos)
        self.assertFalse(Beca.objects.exists())

    def test_descuentos_aplicaciones_y_saldadas_excluidas(self):
        s=self.solicitar()
        for cambios in [{'monto_descuento':Decimal('1')},{'estado':'ANULADA'},{'estado':'PAGADA'}]:
            Obligacion.objects.filter(pk=self.cargo.pk).update(**cambios)
            with self.assertRaises(ValidationError):self.aprobar(s,obligaciones=[self.cargo.pk])
            Obligacion.objects.filter(pk=self.cargo.pk).update(monto_descuento=0,estado='PENDIENTE')
        self.pagar(self.cargo,'20')
        with self.assertRaises(ValidationError):self.aprobar(s,obligaciones=[self.cargo.pk])

    def test_convenio_activo_y_cumplido_excluidos(self):
        convenio=ConvenioPago.objects.create(estudiante=self.estudiante,usuario_autoriza=self.directora,
            fecha_convenio=date(2026,6,1),monto_convenido='20',numero_cuotas=1,estado='ACTIVO')
        ConvenioObligacion.objects.create(convenio=convenio,obligacion=self.cargo,saldo_incluido='20')
        s=self.solicitar()
        for estado in ['ACTIVO','CUMPLIDO']:
            ConvenioPago.objects.filter(pk=convenio.pk).update(estado=estado)
            with self.assertRaises(ValidationError):self.aprobar(s,obligaciones=[self.cargo.pk])

    def test_obligaciones_ajenas_y_listas_manipuladas(self):
        s=self.solicitar()
        for ids in [[self.cargo.pk,self.cargo.pk],[999999],[],['1']]:
            with self.assertRaises(ValidationError):self.aprobar(s,obligaciones=ids)
        with self.assertRaises(ValidationError):self.aprobar(s,conceptos=['MATRICULA'],obligaciones=[self.cargo.pk])
        with self.assertRaises(ValidationError):self.aprobar(s,porcentaje='75')

    def test_rollback_si_falla_aplicacion_o_historial(self):
        s=self.solicitar();antes=list(Obligacion.objects.values())
        for modelo in [AplicacionBeca,SolicitudBeca]:
            with patch.object(modelo,'save',side_effect=DatabaseError('Fallo ficticio')):
                with self.assertRaises(DatabaseError):self.aprobar(s)
            self.assertEqual(list(Obligacion.objects.values()),antes)
            self.assertFalse(Beca.objects.exists());self.assertFalse(AplicacionBeca.objects.exists())
            s.refresh_from_db();self.assertEqual(s.estado,'PENDIENTE')

    def test_decisiones_y_solicitudes_no_se_editan(self):
        s=self.solicitar();s.justificacion='Cambiar'
        with self.assertRaises(ValidationError):s.save()
        s.refresh_from_db();self.aprobar(s);s.refresh_from_db()
        with self.assertRaises(ValidationError):s.save()
        with self.assertRaises(ValidationError):s.delete()

    def test_admin_no_aplica_becas_ni_modifica_descuentos(self):
        request=RequestFactory().get('/admin/');request.user=self.admin
        modelo_admin=admin.site._registry[Beca]
        self.assertFalse(modelo_admin.has_add_permission(request))
        self.assertFalse(modelo_admin.has_change_permission(request))
        self.assertFalse(modelo_admin.has_delete_permission(request))
        self.assertIn('monto_descuento',admin.site._registry[Obligacion].get_readonly_fields(request,self.cargo))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post('/admin/financiero/beca/add/',{}).status_code,403)
        self.assertEqual(self.client.post('/admin/financiero/aplicacionbeca/add/',{}).status_code,404)

    def test_ui_flujo_completo_y_reenvio(self):
        url=reverse('becas_nueva')
        self.assertContains(self.client.get(url),'Justificación')
        datos={'clave':self.clave,'matricula':self.matricula.pk,'porcentaje':'50',
               'conceptos':['MATRICULA','MENSUALIDAD'],'alcance':'AMBAS','justificacion':'Prueba HTTP'}
        self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(self.client.post(url,datos).status_code,302)
        s=SolicitudBeca.objects.get()
        url=reverse('becas_detalle',args=[s.pk])
        self.assertEqual(self.client.post(url,{}).status_code,403)
        self.client.force_login(self.directora)
        datos=self.datos()|{'decision':'APROBADA','accion':'comparar'}
        response=self.client.post(url,datos)
        self.assertContains(response,'Revisión antes de aprobar')
        datos['revision']=response.context['form'].data['revision'];datos['accion']='resolver'
        self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertContains(self.client.get(url),'Autorizado: 50 %')
        self.assertContains(self.client.get(reverse('finanzas_cuenta',args=[self.estudiante.pk])),'Beca #')

    def test_rutas_roles_csrf_y_anonimo(self):
        s=self.solicitar();url=reverse('becas_detalle',args=[s.pk])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('becas_listado')).status_code,200)
        self.assertEqual(self.client.post(url,{'decision':'RECHAZADA','observaciones':'No'}).status_code,403)
        self.assertEqual(self.client.get(reverse('becas_nueva')).status_code,403)
        self.client.force_login(self.docente)
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.logout();self.assertEqual(self.client.get(url).status_code,302)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.directora)
        self.assertEqual(csrf.post(url,{'decision':'RECHAZADA','observaciones':'No'}).status_code,403)

    def test_matricula_inactiva_y_solicitud_obligatoria(self):
        Matricula.objects.filter(pk=self.matricula.pk).update(estado='INACTIVA')
        with self.assertRaises(ValidationError):self.solicitar()
        Matricula.objects.filter(pk=self.matricula.pk).update(estado='ACTIVA')
        s=self.solicitar()
        Matricula.objects.filter(pk=self.matricula.pk).update(estado='INACTIVA')
        with self.assertRaises(ValidationError):self.aprobar(s)
        becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',observaciones='Matrícula inactiva')

    def test_migracion_solo_crea_solicitud_beca(self):
        m=importlib.import_module('financiero.migrations.0001_initial').Migration
        self.assertEqual(len(m.operations),2)
        self.assertEqual(m.operations[0].database_operations,[])
        self.assertTrue(all(op.options.get('managed') is False for op in m.operations[0].state_operations))
        self.assertEqual(m.operations[1].name,'SolicitudBeca')
        self.assertIn('solicitud_beca',connection.introspection.table_names())

    def test_restricciones_base_pendiente_y_porcentaje(self):
        s=self.solicitar()
        with self.assertRaises(IntegrityError),transaction.atomic():
            SolicitudBeca.objects.create(clave=uuid.uuid4(),matricula=self.matricula,solicitante=self.secretaria,
                porcentaje_solicitado=50,conceptos_solicitados=['MATRICULA'],alcance_solicitado='AMBAS',justificacion='Duplicada')
        with self.assertRaises(IntegrityError),transaction.atomic():
            SolicitudBeca.objects.filter(pk=s.pk).update(porcentaje_solicitado=75)

    def test_admin_post_no_puede_cambiar_beca_aplicacion_o_descuento(self):
        self.aprobar(self.solicitar(),obligaciones=[self.cargo.pk])
        beca=Beca.objects.get();self.cargo.refresh_from_db()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f'/admin/financiero/beca/{beca.pk}/change/',{'porcentaje':'100'}).status_code,403)
        self.assertEqual(self.client.post('/admin/financiero/aplicacionbeca/add/',{'monto_aplicado':'100'}).status_code,404)
        datos={f.name: str(getattr(self.cargo,f.attname)) if getattr(self.cargo,f.attname) is not None else ''
               for f in self.cargo._meta.local_fields if not f.primary_key}
        datos['monto_descuento']='19.99'
        response=self.client.post(f'/admin/financiero/obligacion/{self.cargo.pk}/change/',datos)
        self.assertEqual(response.status_code,302)
        self.cargo.refresh_from_db();beca.refresh_from_db()
        self.assertEqual(self.cargo.monto_descuento,Decimal('10'))
        self.assertEqual(beca.porcentaje,Decimal('50'))
        from .admin import AplicacionBecaInline
        req=RequestFactory().get('/admin/');req.user=self.admin
        inline=AplicacionBecaInline(Beca,admin.site)
        self.assertFalse(inline.has_add_permission(req,beca))
        self.assertFalse(inline.has_change_permission(req,beca))
        self.assertFalse(inline.has_delete_permission(req,beca))

    def test_nueva_solicitud_no_reaplica_beca_anterior(self):
        self.aprobar(self.solicitar(),obligaciones=[self.cargo.pk])
        s=self.solicitar(clave=uuid.uuid4())
        with self.assertRaisesMessage(ValidationError,'descuentos'):self.aprobar(s,obligaciones=[self.cargo.pk])
        self.assertEqual(Beca.objects.count(),1)
        self.assertEqual(AplicacionBeca.objects.count(),1)

    def test_firma_obligatoria_y_condiciones_modificadas_no_se_aplican(self):
        s=self.solicitar();datos=self.datos()
        with self.assertRaises(ValidationError):becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',**datos)
        _,token=becas.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        with self.assertRaises(ValidationError):becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**self.datos(porcentaje='100'))
        with self.assertRaises(ValidationError):becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision='alterada',**datos)
        self.assertFalse(Beca.objects.exists())

    def test_cargo_real_de_otro_estudiante_se_rechaza(self):
        otro=Estudiante.objects.create(codigo_estudiante='BECA-E2',nombres='Otro ficticio',apellidos='Prueba',fecha_ingreso=date(2026,1,1),estado='ACTIVO')
        matricula=matricular(estudiante=otro,ciclo=self.ciclo,numero_matricula='BECA-2',fecha_matricula=date(2026,1,2))[0]
        s=self.solicitar()
        with self.assertRaisesMessage(ValidationError,'no pertenece'):self.aprobar(s,obligaciones=[matricula.obligaciones.first().pk])
        self.assertFalse(Beca.objects.exists())

    def test_orden_de_bloqueos_compatible_con_cobro(self):
        original=QuerySet.select_for_update;orden=[]
        def observar(qs,*args,**kwargs):
            orden.append(qs.model.__name__)
            return original(qs,*args,**kwargs)
        s=self.solicitar();datos=self.datos(obligaciones=[self.cargo.pk])
        _,token=becas.previsualizar(usuario=self.directora,solicitud_id=s.pk,**datos)
        with patch.object(QuerySet,'select_for_update',observar):
            becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=token,**datos)
        self.assertEqual(orden,['Usuario','Estudiante','Matricula','Obligacion','SolicitudBeca'])
        orden.clear()
        with patch.object(QuerySet,'select_for_update',observar):self.pagar(self.cargo,'5')
        self.assertEqual(orden[:4],['Usuario','Caja','Estudiante','Obligacion'])

    def test_pagos_posteriores_beca_cien_no_admiten_cobro_inexistente(self):
        self.aprobar(self.solicitar(),porcentaje='100',obligaciones=[self.cargo.pk])
        with self.assertRaises(ValidationError):self.pagar(self.cargo,'1')
        self.assertFalse(Pago.objects.exists())

    def test_concepto_matricula_con_tilde_se_aplica_consistentemente(self):
        o=next(o for o in self.obligaciones if o.concepto.nombre=='MATRICULA')
        o.concepto.nombre='MATRÍCULA';o.concepto.save()
        self.aprobar(self.solicitar(),conceptos=['MATRICULA'],obligaciones=[o.pk])
        self.assertEqual(AplicacionBeca.objects.count(),1)

    def test_cambio_de_identidad_matricula_impide_aprobar(self):
        s=self.solicitar()
        Matricula.objects.filter(pk=self.matricula.pk).update(numero_matricula='OTRO-NUMERO')
        with self.assertRaisesMessage(ValidationError,'matrícula cambió'):self.aprobar(s)
        becas.resolver(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',observaciones='Matrícula modificada')
        self.assertFalse(Beca.objects.exists())

    def test_etiqueta_matricula_identifica_estudiante_y_ciclo(self):
        self.assertContains(self.client.get(reverse('becas_nueva')),self.estudiante.codigo_estudiante)
        self.assertContains(self.client.get(reverse('becas_nueva')),'BECA-1')
