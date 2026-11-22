"""F5: datos sintéticos, documentos en SQLite efímero y regresión de caja."""
import io
import uuid
import importlib
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from PIL import Image
from pypdf import PdfWriter
from django.contrib import admin
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError,IntegrityError,transaction,connection
from django.db.models.query import QuerySet
from django.test import TestCase,Client,RequestFactory
from django.urls import reverse
from django.utils import timezone
from core.models import Usuario
from . import operaciones,caja,anulaciones,comprobantes
from .models import (Ingreso,Egreso,CategoriaIngreso,CategoriaEgreso,MovimientoCaja,RegistroIngreso,
    SolicitudEgreso,DesembolsoEgreso,SolicitudAnulacionOperacion,ComprobantePrivado,Caja,Pago)


class OperacionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_caja import CajaTests
        CajaTests.setUpTestData.__func__(cls)

    def setUp(self):
        from .test_caja import CajaTests
        CajaTests.setUp(self)
        self.ci=CategoriaIngreso.objects.create(nombre='Materiales',estado='ACTIVO')
        self.ce=CategoriaEgreso.objects.create(nombre='Servicios',estado='ACTIVO',requiere_autorizacion=False)
        self.fecha=timezone.now()-timedelta(minutes=1)

    def ingreso(self,**cambios):
        return operaciones.registrar_ingreso(**(dict(usuario=self.secretaria,clave=uuid.uuid4(),categoria_id=self.ci.pk,
            concepto='Venta de libro',origen='Persona ficticia',monto='30',metodo='EFECTIVO',referencia='F5',fecha=self.fecha)|cambios))

    def solicitar(self,**cambios):
        return operaciones.solicitar_egreso(**(dict(usuario=self.secretaria,clave=uuid.uuid4(),categoria_id=self.ce.pk,
            concepto='Pago de servicio',beneficiario='Proveedor ficticio',monto='5',justificacion='Necesidad institucional ficticia')|cambios))

    def aprobar(self,s,**cambios):
        return operaciones.decidir_egreso(**(dict(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA')|cambios))

    def desembolsar(self,s=None,**cambios):
        s=s or self.aprobar(self.solicitar())
        return operaciones.desembolsar(**(dict(usuario=self.secretaria,clave=uuid.uuid4(),solicitud_id=s.pk,
            metodo='EFECTIVO',referencia='EG-F5',fecha=self.fecha)|cambios))

    def pedir_anulacion(self,r=None,tipo='INGRESO',**cambios):
        r=r or self.ingreso()
        return operaciones.solicitar_anulacion(**(dict(usuario=self.secretaria,tipo=tipo,registro_id=r.pk,
            clave=uuid.uuid4(),motivo='Error ficticio de registro')|cambios))

    def anular(self,s,**cambios):
        datos=dict(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA')|cambios
        revision=operaciones.decidir_anulacion(**datos)
        return operaciones.decidir_anulacion(**datos,revision=revision,confirmar=True)

    def cerrar(self):
        t=caja.totales(self.caja)
        datos=dict(usuario=self.secretaria,caja_id=self.caja.pk,contado=t['esperado'])
        _,rev=caja.preparar_cierre(**datos)
        return caja.cerrar(**datos,revision=rev)

    def png(self):
        b=io.BytesIO();Image.new('RGB',(3,3),'blue').save(b,format='PNG')
        return SimpleUploadedFile('../../comprobante.exe',b.getvalue(),content_type='text/html')

    def pdf(self,activo=False):
        b=io.BytesIO();w=PdfWriter();w.add_blank_page(width=100,height=100)
        if activo:w.add_js('app.alert("prueba")')
        w.write(b)
        return SimpleUploadedFile('prueba.pdf',b.getvalue(),content_type='application/pdf')

    def test_ingreso_valido_reutiliza_modelo_y_movimiento(self):
        r=self.ingreso()
        self.assertEqual(Ingreso.objects.count(),1)
        self.assertFalse(Pago.objects.exists())
        self.assertTrue(r.numero.startswith('ING-'))
        m=MovimientoCaja.objects.get()
        self.assertEqual(m.ingreso_id,r.ingreso_id);self.assertIsNone(m.pago_id)
        self.assertEqual(Decimal(caja.totales(self.caja)['esperado']),40)

    def test_ingreso_transferencia_no_aumenta_efectivo(self):
        self.ingreso(metodo='TRANSFERENCIA')
        t=caja.totales(self.caja)
        self.assertEqual(Decimal(t['esperado']),10)
        self.assertEqual(Decimal(t['transferencias_vigentes']),30)

    def test_ingreso_uuid_idempotente_y_datos_diferentes_rechazados(self):
        clave=uuid.uuid4();r=self.ingreso(clave=clave)
        self.assertEqual(self.ingreso(clave=clave).pk,r.pk)
        with self.assertRaises(ValidationError):self.ingreso(clave=clave,monto='31')
        self.assertEqual(MovimientoCaja.objects.count(),1)

    def test_ingreso_mismos_datos_nueva_clave_no_duplica(self):
        self.ingreso()
        with self.assertRaisesMessage(ValidationError,'mismos datos'):self.ingreso()
        self.assertEqual(Ingreso.objects.count(),1)

    def test_ingreso_caja_obligatoria(self):
        self.cerrar()
        with self.assertRaises(ValidationError):self.ingreso()
        self.assertFalse(Ingreso.objects.exists())

    def test_importes_invalidos(self):
        for monto in ('0','-1','1.001','NaN','Infinity','100000000'):
            with self.subTest(monto=monto),self.assertRaises(ValidationError):self.ingreso(monto=monto)
        self.assertFalse(Ingreso.objects.exists())

    def test_fecha_futura_bloqueada(self):
        with self.assertRaises(ValidationError):self.ingreso(fecha=timezone.now()+timedelta(days=1))

    def test_categoria_inactiva_bloquea_ingreso_y_solicitud(self):
        CategoriaIngreso.objects.filter(pk=self.ci.pk).update(estado='INACTIVO')
        CategoriaEgreso.objects.filter(pk=self.ce.pk).update(estado='INACTIVO')
        with self.assertRaises(ValidationError):self.ingreso()
        with self.assertRaises(ValidationError):self.solicitar()

    def test_conceptos_reservados_sin_pago_academico_ficticio(self):
        for concepto in ('Matrícula de estudiante','Mensualidad de ciclo','Convenio de pago','Donación','Padrinazgo'):
            with self.subTest(concepto=concepto),self.assertRaises(ValidationError):self.ingreso(concepto=concepto)
        CategoriaIngreso.objects.filter(pk=self.ci.pk).update(nombre='MATRICULA')
        with self.assertRaises(ValidationError):self.ingreso()
        self.assertFalse(Ingreso.objects.exists());self.assertFalse(Pago.objects.exists())

    def test_solicitud_no_es_egreso_ni_salida(self):
        antes=caja.totales(self.caja);s=self.solicitar()
        self.assertEqual(s.estado,'PENDIENTE');self.assertEqual(caja.totales(self.caja),antes)
        self.assertFalse(Egreso.objects.exists())

    def test_aprobacion_no_desembolsa_aun_categoria_no_exige(self):
        antes=caja.totales(self.caja);s=self.aprobar(self.solicitar())
        self.assertEqual(s.estado,'APROBADA');self.assertEqual(caja.totales(self.caja),antes)
        self.assertFalse(Egreso.objects.exists())

    def test_solicitud_uuid_idempotente(self):
        clave=uuid.uuid4();s=self.solicitar(clave=clave)
        self.assertEqual(self.solicitar(clave=clave).pk,s.pk)
        with self.assertRaises(ValidationError):self.solicitar(clave=clave,monto='7')

    def test_solo_directora_activa_aprueba_incluso_admin_superusuario(self):
        s=self.solicitar()
        for actor in (self.secretaria,self.admin,self.docente):
            with self.assertRaises(PermissionDenied):self.aprobar(s,usuario=actor)
        Usuario.objects.filter(pk=self.directora.pk).update(estado_cuenta='INACTIVA')
        with self.assertRaises(PermissionDenied):self.aprobar(s)

    def test_cambio_rol_solicitante_bloquea_aprobacion(self):
        s=self.solicitar();Usuario.objects.filter(pk=self.secretaria.pk).update(rol='MAESTRO')
        with self.assertRaises(ValidationError):self.aprobar(s)

    def test_aprobacion_idempotente_y_contradictoria(self):
        s=self.solicitar();self.aprobar(s);self.aprobar(s)
        with self.assertRaises(ValidationError):self.aprobar(s,decision='RECHAZADA',resolucion='Cambiar')
        self.assertFalse(Egreso.objects.exists())

    def test_rechazo_exige_motivo_y_no_mueve_dinero(self):
        s=self.solicitar()
        with self.assertRaises(ValidationError):self.aprobar(s,decision='RECHAZADA')
        self.aprobar(s,decision='RECHAZADA',resolucion='No procede')
        with self.assertRaises(ValidationError):self.desembolsar(s)
        self.assertFalse(Egreso.objects.exists())

    def test_desembolso_sin_autorizacion_bloqueado(self):
        with self.assertRaises(ValidationError):self.desembolsar(self.solicitar())
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_desembolso_valido_importe_original_salida_de_caja(self):
        s=self.aprobar(self.solicitar());d=self.desembolsar(s)
        self.assertEqual(d.egreso.monto,s.monto)
        self.assertEqual(d.egreso.usuario_autoriza_id,self.directora.pk)
        self.assertEqual(d.egreso.fecha_autorizacion,s.fecha_resolucion)
        self.assertEqual(Decimal(caja.totales(self.caja)['esperado']),5)
        self.assertEqual(MovimientoCaja.objects.get().egreso_id,d.egreso_id)

    def test_disponible_insuficiente_bloquea_todo(self):
        s=self.aprobar(self.solicitar(monto='10.01'))
        with self.assertRaisesMessage(ValidationError,'insuficiente'):self.desembolsar(s)
        self.assertFalse(Egreso.objects.exists());self.assertFalse(DesembolsoEgreso.objects.exists())

    def test_transferencia_salida_no_afecta_efectivo(self):
        d=self.desembolsar(self.aprobar(self.solicitar(monto='100')),metodo='TRANSFERENCIA')
        self.assertEqual(Decimal(caja.totales(self.caja)['esperado']),10)
        self.assertEqual(Decimal(caja.totales(self.caja)['transferencias_realizadas']),100)

    def test_ejemplo_arqueo_10_mas_100_mas_30_menos_40(self):
        from .test_caja import CajaTests
        CajaTests.pagar(self,'100',aplicaciones=[(o.pk,Decimal('20')) for o in self.obligaciones[:5]])
        self.ingreso()
        self.desembolsar(self.aprobar(self.solicitar(monto='40')))
        t=caja.totales(self.caja)
        self.assertEqual(Decimal(t['esperado']),100)
        self.assertEqual(Decimal(t['academicos_efectivo']),100)
        self.assertEqual(Decimal(t['administrativos_efectivo']),30)
        self.assertEqual(Decimal(t['salidas_efectivo']),40)

    def test_desembolso_reenvio_y_segunda_clave(self):
        s=self.aprobar(self.solicitar());clave=uuid.uuid4();d=self.desembolsar(s,clave=clave)
        self.assertEqual(self.desembolsar(s,clave=clave).pk,d.pk)
        with self.assertRaises(ValidationError):self.desembolsar(s)
        with self.assertRaises(ValidationError):self.desembolsar(s,clave=clave,referencia='Otra')
        self.assertEqual(Egreso.objects.count(),1)

    def test_caja_cerrada_bloquea_nuevo_desembolso(self):
        s=self.aprobar(self.solicitar());self.cerrar()
        with self.assertRaises(ValidationError):self.desembolsar(s)

    def test_reenvio_desembolso_tras_cierre_conserva_original(self):
        s=self.aprobar(self.solicitar());clave=uuid.uuid4();d=self.desembolsar(s,clave=clave);self.cerrar()
        self.assertEqual(self.desembolsar(s,clave=clave).pk,d.pk)

    def test_secretaria_no_desembolsa_solicitudes_ajenas(self):
        s=self.aprobar(self.solicitar(usuario=self.admin))
        with self.assertRaises(PermissionDenied):self.desembolsar(s)

    def test_admin_ejecuta_solicitud_autorizada_sin_aprobar(self):
        s=self.aprobar(self.solicitar())
        caja.abrir(usuario=self.admin,clave=uuid.uuid4(),fondo='10')
        d=self.desembolsar(s,usuario=self.admin)
        self.assertEqual(d.egreso.usuario_registra_id,self.admin.pk)

    def test_rollback_ingreso_y_documento_si_falla_movimiento(self):
        with patch.object(MovimientoCaja,'save',side_effect=DatabaseError('Ficticio')),self.assertRaises(DatabaseError):self.ingreso(archivo=self.png())
        for modelo in (Ingreso,RegistroIngreso,ComprobantePrivado):self.assertFalse(modelo.objects.exists())

    def test_rollback_desembolso_y_documento(self):
        s=self.aprobar(self.solicitar())
        with patch.object(MovimientoCaja,'save',side_effect=DatabaseError('Ficticio')),self.assertRaises(DatabaseError):self.desembolsar(s,archivo=self.png())
        self.assertFalse(Egreso.objects.exists());self.assertFalse(ComprobantePrivado.objects.exists())
        self.assertEqual(SolicitudEgreso.objects.get(pk=s.pk).estado,'APROBADA')

    def test_rollback_decision_despues_guardar(self):
        s=self.solicitar();original=SolicitudEgreso.save
        def fallar(obj,*a,**k):original(obj,*a,**k);raise DatabaseError('Ficticio')
        with patch.object(SolicitudEgreso,'save',fallar),self.assertRaises(DatabaseError):self.aprobar(s)
        self.assertEqual(SolicitudEgreso.objects.get(pk=s.pk).estado,'PENDIENTE')

    def test_resolucion_y_registros_inmutables(self):
        r=self.ingreso();s=self.aprobar(self.solicitar());d=self.desembolsar(s)
        for obj in (r,s,d):
            with self.assertRaises(ValidationError):obj.save()
            with self.assertRaises(ValidationError):obj.delete()

    def test_documento_png_valida_contenido_no_extension(self):
        r=self.ingreso(archivo=self.png());d=r.comprobante
        self.assertEqual(d.mime,'image/png');self.assertTrue(d.nombre.endswith('.png'))
        self.assertNotIn('..',d.nombre)
        self.assertEqual(bytes(d.contenido)[:8],b'\x89PNG\r\n\x1a\n')

    def test_pdf_real_permitido_activo_cifrado_o_corrupto_bloqueado(self):
        self.assertEqual(comprobantes.validar_archivo(self.pdf())['mime'],'application/pdf')
        for archivo in (self.pdf(activo=True),SimpleUploadedFile('x.pdf',b'%PDF-1.7\nmalformado')):
            with self.assertRaises(ValidationError):comprobantes.validar_archivo(archivo)
        b=io.BytesIO();w=PdfWriter();w.add_blank_page(width=100,height=100);w.encrypt('ficticia');w.write(b)
        with self.assertRaises(ValidationError):comprobantes.validar_archivo(SimpleUploadedFile('x.pdf',b.getvalue()))

    def test_documentos_html_svg_vacios_y_tamano_bloqueados(self):
        for contenido in (b'<html>Ejecutable</html>',b'<svg onload="alert(1)"/>',b'',b'x'*(5*1024*1024+1)):
            with self.assertRaises(ValidationError):comprobantes.validar_archivo(SimpleUploadedFile('x.png',contenido))

    def test_documento_privado_autorizado_y_hash_verificado(self):
        r=self.ingreso(archivo=self.png());url=reverse('operaciones_documento',args=[r.comprobante_id])
        resp=self.client.get(url);self.assertEqual(resp.status_code,200)
        self.assertIn('attachment;',resp['Content-Disposition']);self.assertEqual(resp['Cache-Control'],'private, no-store')
        self.client.force_login(self.otra);self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.directora);self.assertEqual(self.client.get(url).status_code,200)
        self.client.logout();self.assertEqual(self.client.get(url).status_code,302)
        ComprobantePrivado.objects.filter(pk=r.comprobante_id).update(sha256='0'*64)
        self.client.force_login(self.secretaria);self.assertEqual(self.client.get(url).status_code,503)

    def test_documentos_solicitud_y_pago_permanecen_tras_anulacion(self):
        s=self.aprobar(self.solicitar(archivo=self.pdf()));d=self.desembolsar(s,archivo=self.png())
        self.anular(self.pedir_anulacion(d,tipo='EGRESO'))
        self.assertEqual(ComprobantePrivado.objects.count(),2)
        for pk in (s.comprobante_id,d.comprobante_id):self.assertEqual(self.client.get(reverse('operaciones_documento',args=[pk])).status_code,200)

    def test_anulacion_ingreso_no_devuelve_efectivo_y_reserva_disponible(self):
        r=self.ingreso();s=self.pedir_anulacion(r);self.anular(s)
        t=caja.totales(self.caja)
        self.assertEqual(Decimal(t['esperado']),40)
        self.assertEqual(Decimal(t['disponible']),10)
        self.assertEqual(Decimal(t['efectivo_anulado_retenido']),30)
        self.assertEqual(Ingreso.objects.get(pk=r.ingreso_id).estado,'ANULADO')

    def test_efectivo_anulado_no_financia_desembolso(self):
        self.anular(self.pedir_anulacion())
        s=self.aprobar(self.solicitar(monto='11'))
        with self.assertRaisesMessage(ValidationError,'insuficiente'):self.desembolsar(s)

    def test_anulacion_ingreso_gastado_bloqueada(self):
        r=self.ingreso();self.desembolsar(self.aprobar(self.solicitar(monto='20')))
        with self.assertRaisesMessage(ValidationError,'disponible insuficiente'):self.pedir_anulacion(r)

    def test_desembolso_posterior_bloquea_aprobacion_anulacion(self):
        r=self.ingreso();s=self.pedir_anulacion(r)
        self.desembolsar(self.aprobar(self.solicitar(monto='20')))
        with self.assertRaises(ValidationError):self.anular(s)
        self.assertEqual(Ingreso.objects.get(pk=r.ingreso_id).estado,'REGISTRADO')

    def test_f4_anulacion_academica_no_puede_dejar_reserva_sin_fondos(self):
        from .test_caja import CajaTests
        p=CajaTests.pagar(self)
        s=anulaciones.solicitar(usuario=self.secretaria,pago_id=p.pk,motivo='Ficticio',clave=uuid.uuid4())
        self.desembolsar(self.aprobar(self.solicitar(monto='20')))
        with self.assertRaisesMessage(ValidationError,'respalda desembolsos'):anulaciones.previsualizar(usuario=self.directora,solicitud_id=s.pk)
        self.assertEqual(Pago.objects.get(pk=p.pk).estado,'REGISTRADO')

    def test_anulacion_egreso_no_recupera_efectivo(self):
        d=self.desembolsar();antes=caja.totales(self.caja)
        self.anular(self.pedir_anulacion(d,tipo='EGRESO'))
        t=caja.totales(self.caja)
        self.assertEqual(t['esperado'],antes['esperado'])
        self.assertEqual(Decimal(t['egresos_anulados_efectivo']),5)
        self.assertEqual(Egreso.objects.get(pk=d.egreso_id).estado,'ANULADO')

    def test_anulacion_transferencia_no_modifica_efectivo(self):
        self.anular(self.pedir_anulacion(self.ingreso(metodo='TRANSFERENCIA')))
        t=caja.totales(self.caja)
        self.assertEqual(Decimal(t['esperado']),10)
        self.assertEqual(Decimal(t['transferencias_vigentes']),0)

    def test_cajas_cerradas_foto_intacta_y_anulaciones_bloqueadas(self):
        r=self.ingreso();s=self.pedir_anulacion(r);c=self.cerrar();foto=c.cierre
        with self.assertRaises(ValidationError):self.anular(s)
        c.refresh_from_db();self.assertEqual(c.cierre,foto)
        self.assertEqual(Ingreso.objects.get(pk=r.ingreso_id).estado,'REGISTRADO')

    def test_rechazo_anulacion_no_modifica_movimientos(self):
        r=self.ingreso();s=self.pedir_anulacion(r);antes=caja.totales(self.caja)
        with self.assertRaises(ValidationError):operaciones.decidir_anulacion(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA')
        operaciones.decidir_anulacion(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',resolucion='No procede')
        self.assertEqual(caja.totales(self.caja),antes)

    def test_anulacion_uuid_y_pendiente_duplicada(self):
        r=self.ingreso();clave=uuid.uuid4();s=self.pedir_anulacion(r,clave=clave)
        self.assertEqual(self.pedir_anulacion(r,clave=clave).pk,s.pk)
        with self.assertRaises(ValidationError):self.pedir_anulacion(r)
        with self.assertRaises(ValidationError):self.pedir_anulacion(r,clave=clave,motivo='Otro')

    def test_anulacion_aprobacion_repetida_contradictoria(self):
        s=self.pedir_anulacion();self.anular(s)
        self.assertEqual(operaciones.decidir_anulacion(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',confirmar=True).pk,s.pk)
        with self.assertRaises(ValidationError):operaciones.decidir_anulacion(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',resolucion='Otro')

    def test_anulacion_solo_directora_y_solicitante_vigente(self):
        s=self.pedir_anulacion()
        for actor in (self.secretaria,self.admin,self.docente):
            with self.assertRaises(PermissionDenied):self.anular(s,usuario=actor)
        Usuario.objects.filter(pk=self.secretaria.pk).update(rol='MAESTRO')
        with self.assertRaises(ValidationError):self.anular(s)

    def test_anulacion_datos_obsoletos_y_firma_alterada(self):
        r=self.ingreso();s=self.pedir_anulacion(r)
        with self.assertRaises(ValidationError):operaciones.decidir_anulacion(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',confirmar=True,revision='alterado')
        Ingreso.objects.filter(pk=r.ingreso_id).update(referencia='Otra')
        with self.assertRaises(ValidationError):self.anular(s)

    def test_rollback_anulacion_conserva_estado_original(self):
        r=self.ingreso();s=self.pedir_anulacion(r);original=SolicitudAnulacionOperacion.save
        def fallar(obj,*a,**k):original(obj,*a,**k);raise DatabaseError('Ficticio')
        with patch.object(SolicitudAnulacionOperacion,'save',fallar),self.assertRaises(DatabaseError):self.anular(s)
        self.assertEqual(Ingreso.objects.get(pk=r.ingreso_id).estado,'REGISTRADO')
        self.assertEqual(SolicitudAnulacionOperacion.objects.get(pk=s.pk).estado,'PENDIENTE')

    def test_admin_puede_solicitar_anulacion_propia_sin_autorizar(self):
        caja.abrir(usuario=self.admin,clave=uuid.uuid4(),fondo='0')
        r=self.ingreso(usuario=self.admin)
        s=self.pedir_anulacion(r,usuario=self.admin)
        with self.assertRaises(PermissionDenied):self.anular(s,usuario=self.admin)
        self.anular(s)

    def test_anulacion_movimiento_ajeno_denegada(self):
        r=self.ingreso()
        with self.assertRaises(PermissionDenied):self.pedir_anulacion(r,usuario=self.otra)

    def test_categoria_configuracion_solo_admin_sin_borrar_historia(self):
        r=self.ingreso()
        for actor in (self.secretaria,self.directora):
            with self.assertRaises(PermissionDenied):operaciones.configurar_categoria(usuario=actor,tipo='INGRESO',nombre='Otra')
        operaciones.configurar_categoria(usuario=self.admin,tipo='INGRESO',categoria_id=self.ci.pk,estado='INACTIVO')
        self.assertEqual(RegistroIngreso.objects.get(pk=r.pk).ingreso.monto,30)
        self.assertEqual(self.client.get(reverse('operaciones_ingreso',args=[r.pk])).status_code,200)

    def test_categoria_creacion_duplicado_y_reservadas(self):
        c=operaciones.configurar_categoria(usuario=self.admin,tipo='EGRESO',nombre='Mantenimiento')
        self.assertTrue(c.requiere_autorizacion)
        with self.assertRaises(ValidationError):operaciones.configurar_categoria(usuario=self.admin,tipo='EGRESO',nombre='mantenimiento')
        with self.assertRaises(ValidationError):operaciones.configurar_categoria(usuario=self.admin,tipo='INGRESO',nombre='Mensualidades')

    def test_restriccion_origen_unico_movimiento(self):
        r=self.ingreso()
        with self.assertRaises(ValidationError):MovimientoCaja.objects.create(caja=self.caja,operador=self.secretaria,metodo='EFECTIVO',importe=1)
        with self.assertRaises(IntegrityError),transaction.atomic():MovimientoCaja.objects.filter(ingreso=r.ingreso).update(ingreso=None)

    def test_desembolso_solicitud_unico_bd(self):
        d=self.desembolsar()
        with self.assertRaises(IntegrityError),transaction.atomic():DesembolsoEgreso.objects.create(clave=uuid.uuid4(),solicitud=d.solicitud,egreso=d.egreso,datos={})

    def test_admin_no_tiene_rutas_alternativas(self):
        request=RequestFactory().get('/admin/');request.user=self.admin
        for modelo in (Ingreso,Egreso,CategoriaIngreso,CategoriaEgreso):
            a=admin.site._registry[modelo]
            self.assertFalse(a.has_add_permission(request));self.assertFalse(a.has_change_permission(request));self.assertFalse(a.has_delete_permission(request))
        for modelo in (RegistroIngreso,SolicitudEgreso,DesembolsoEgreso,ComprobantePrivado,SolicitudAnulacionOperacion):self.assertNotIn(modelo,admin.site._registry)

    def test_orden_bloqueos_caja_antes_origen(self):
        orden=[];original=QuerySet.select_for_update
        def observar(q,*a,**k):orden.append(q.model.__name__);return original(q,*a,**k)
        with patch.object(QuerySet,'select_for_update',observar):self.ingreso()
        self.assertEqual(orden[:3],['Usuario','Caja','CategoriaIngreso'])
        orden.clear();s=self.aprobar(self.solicitar())
        with patch.object(QuerySet,'select_for_update',observar):self.desembolsar(s)
        self.assertEqual(orden[:4],['Usuario','Caja','CategoriaEgreso','SolicitudEgreso'])

    def test_rutas_y_documentos_sin_nuevos_permisos(self):
        r=self.ingreso(archivo=self.png());s=self.solicitar()
        urls=[reverse('operaciones_panel'),reverse('operaciones_ingreso',args=[r.pk]),reverse('operaciones_egreso',args=[s.pk]),
            reverse('operaciones_documento',args=[r.comprobante_id]),reverse('operaciones_reporte'),reverse('operaciones_categorias')]
        for rol in ('MAESTRO','ESTUDIANTE','PASTOR_PRINCIPAL'):
            actor=Usuario.objects.create_user('f5-'+rol,rol+'@example.test','ficticia',rol=rol);self.client.force_login(actor)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code,403);self.assertEqual(self.client.post(url,{}).status_code,403)
        self.client.force_login(self.otra)
        self.assertEqual(self.client.get(urls[1]).status_code,404);self.assertEqual(self.client.get(urls[2]).status_code,404)
        self.assertEqual(self.client.get(urls[4]).status_code,403)

    def test_http_ingreso_y_reenvio_sin_segunda_contabilizacion(self):
        datos={'clave':str(uuid.uuid4()),'categoria':self.ci.pk,'concepto':'Venta de material','origen':'Ficticio',
            'monto':'30','metodo':'EFECTIVO','referencia':'HTTP','fecha':self.fecha.isoformat()}
        url=reverse('operaciones_ingreso_nuevo')
        self.assertEqual(self.client.get(url).status_code,200)
        for _ in range(2):self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(Ingreso.objects.count(),1);self.assertEqual(MovimientoCaja.objects.count(),1)

    def test_http_solicitud_aprobacion_y_desembolso_importe_manipulado_ignorado(self):
        url=reverse('operaciones_egreso_nuevo')
        datos={'clave':str(uuid.uuid4()),'categoria':self.ce.pk,'concepto':'Servicio','beneficiario':'Ficticio','monto':'5','justificacion':'Ficticia'}
        self.assertEqual(self.client.post(url,datos).status_code,302);s=SolicitudEgreso.objects.get()
        url=reverse('operaciones_egreso',args=[s.pk]);self.client.force_login(self.admin)
        self.assertEqual(self.client.post(url,{'decision':'APROBADA'}).status_code,403)
        self.client.force_login(self.directora)
        self.assertEqual(self.client.post(url,{'decision':'APROBADA','monto':'100','directora':self.admin.pk}).status_code,302)
        self.client.force_login(self.secretaria)
        datos={'clave':str(uuid.uuid4()),'metodo':'EFECTIVO','referencia':'','fecha':self.fecha.isoformat(),'monto':'0.01'}
        self.assertEqual(self.client.post(reverse('operaciones_desembolso',args=[s.pk]),datos).status_code,302)
        self.assertEqual(Egreso.objects.get().monto,5)

    def test_http_anulacion_comparacion_y_aprobacion(self):
        r=self.ingreso();url=reverse('operaciones_anular',args=['INGRESO',r.pk])
        self.assertEqual(self.client.post(url,{'clave':str(uuid.uuid4()),'motivo':'Error ficticio'}).status_code,302)
        s=SolicitudAnulacionOperacion.objects.get();url=reverse('operaciones_anulacion',args=[s.pk]);self.client.force_login(self.directora)
        resp=self.client.post(url,{'decision':'APROBADA'})
        self.assertContains(resp,'Confirmar aprobación definitiva')
        datos={'decision':'APROBADA','revision':resp.context['form'].data['revision'],'accion':'confirmar'}
        for _ in range(2):self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertContains(self.client.get(reverse('operaciones_ingreso',args=[r.pk])),'ANULADO')

    def test_http_csrf_y_categoria_no_autorizada(self):
        c=Client(enforce_csrf_checks=True);c.force_login(self.secretaria)
        self.assertEqual(c.post(reverse('operaciones_ingreso_nuevo'),{}).status_code,403)
        self.assertEqual(self.client.post(reverse('operaciones_categorias'),{'tipo':'EGRESO','nombre':'Otro','estado':'ACTIVO'}).status_code,403)

    def test_reporte_separa_solicitudes_autorizaciones_y_pagados(self):
        self.ingreso();pendiente=self.solicitar();autorizado=self.aprobar(self.solicitar(monto='7'));pagado=self.desembolsar()
        self.client.force_login(self.directora);url=reverse('operaciones_reporte')
        resp=self.client.get(url)
        self.assertEqual(resp.context['total_ingresos'],30);self.assertEqual(resp.context['total_egresos'],5)
        self.assertEqual(len(resp.context['pagina']),4)
        resp=self.client.get(url,{'estado':'APROBADA'})
        self.assertEqual(len(resp.context['pagina']),1);self.assertEqual(resp.context['total_egresos'],0)
        resp=self.client.get(url,{'metodo':'EFECTIVO','categoria':'Materiales','operador':self.secretaria.pk})
        self.assertEqual(len(resp.context['pagina']),1)
        self.assertEqual(self.client.get(url,{'desde':'invalida'}).context['total_ingresos'],0)

    def test_reporte_excluye_anulados_sin_duplicar_cobros_academicos(self):
        from .test_caja import CajaTests
        CajaTests.pagar(self);r=self.ingreso();self.anular(self.pedir_anulacion(r))
        self.client.force_login(self.admin)
        resp=self.client.get(reverse('operaciones_reporte'))
        self.assertEqual(resp.context['total_ingresos'],0)
        self.assertEqual(len(resp.context['pagina']),1)

    def test_csv_neutraliza_formulas_e_imprime(self):
        self.ingreso(concepto='=SUM(1,1)');self.client.force_login(self.admin)
        url=reverse('operaciones_reporte');resp=self.client.get(url,{'formato':'csv'})
        self.assertEqual(resp.status_code,200);self.assertIn("'=SUM(1,1)",resp.content.decode('utf-8-sig'))
        self.assertContains(self.client.get(url),'Imprimir reporte')

    def test_esquema_nuevo_sin_ddl_historico(self):
        m=importlib.import_module('financiero.migrations.0004_ingresos_egresos_institucionales')
        permitidos={'comprobanteprivado','registroingreso','solicitudegreso','desembolsoegreso','solicitudanulacionoperacion','movimientocaja'}
        for op in m.Migration.operations:
            self.assertIn((getattr(op,'model_name',None) or getattr(op,'name','')).lower(),permitidos)
        tablas=set(connection.introspection.table_names())
        self.assertTrue({'comprobante_privado','registro_ingreso','solicitud_egreso','desembolso_egreso','solicitud_anulacion_operacion'}<=tablas)

    def test_importe_manipulado_tras_aprobacion_no_se_desembolsa(self):
        s=self.aprobar(self.solicitar())
        SolicitudEgreso.objects.filter(pk=s.pk).update(monto='6')
        with self.assertRaisesMessage(ValidationError,'valores originales'):self.desembolsar(s)
        self.assertFalse(Egreso.objects.exists())

    def test_directora_o_resolucion_manipulada_no_desembolsa(self):
        s=self.aprobar(self.solicitar())
        SolicitudEgreso.objects.filter(pk=s.pk).update(directora=self.admin)
        with self.assertRaisesMessage(ValidationError,'valores definitivos'):self.desembolsar(s)

    def test_ingreso_alterado_no_puede_anular_otros_importes(self):
        r=self.ingreso()
        Ingreso.objects.filter(pk=r.ingreso_id).update(monto='3')
        with self.assertRaisesMessage(ValidationError,'no coincide'):self.pedir_anulacion(r)

    def test_reenvio_http_categoria_inactiva_recupera_ingreso_existente(self):
        datos={'clave':str(uuid.uuid4()),'categoria':self.ci.pk,'concepto':'Venta de material','origen':'Ficticio',
            'monto':'30','metodo':'EFECTIVO','referencia':'HTTP','fecha':self.fecha.isoformat()}
        url=reverse('operaciones_ingreso_nuevo')
        self.assertEqual(self.client.post(url,datos).status_code,302)
        CategoriaIngreso.objects.filter(pk=self.ci.pk).update(estado='INACTIVO')
        self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(Ingreso.objects.count(),1)

    def test_reenvio_aprobacion_categoria_inactiva_no_cambia_decision(self):
        s=self.aprobar(self.solicitar())
        CategoriaEgreso.objects.filter(pk=self.ce.pk).update(estado='INACTIVO')
        self.assertEqual(self.aprobar(s).pk,s.pk)
        with self.assertRaises(ValidationError):self.desembolsar(s)

    def test_http_direccion_no_registra_ingresos_ni_ejecuta_desembolsos(self):
        s=self.aprobar(self.solicitar());self.client.force_login(self.directora)
        for url in (reverse('operaciones_ingreso_nuevo'),reverse('operaciones_egreso_nuevo'),reverse('operaciones_desembolso',args=[s.pk])):
            self.assertEqual(self.client.get(url).status_code,403)
            self.assertEqual(self.client.post(url,{}).status_code,403)

    def test_documento_no_tiene_url_publica_y_decisiones_preservan_identidad(self):
        r=self.ingreso(archivo=self.png())
        self.assertEqual(self.client.get('/media/'+r.comprobante.nombre).status_code,404)
        s=self.solicitar();self.client.force_login(self.directora)
        self.client.post(reverse('operaciones_egreso',args=[s.pk]),{'decision':'APROBADA','directora':self.admin.pk})
        s.refresh_from_db();self.assertEqual(s.directora_id,self.directora.pk)

    def test_rechazo_anulacion_caja_cerrada_conserva_foto(self):
        s=self.pedir_anulacion();c=self.cerrar();foto=c.cierre
        operaciones.decidir_anulacion(usuario=self.directora,solicitud_id=s.pk,decision='RECHAZADA',resolucion='Caja cerrada')
        c.refresh_from_db();self.assertEqual(c.cierre,foto)

    def test_migracion_preserva_movimiento_y_cierre_f4_en_otra_memoria(self):
        from django.db import connections
        from django.db.migrations.loader import MigrationLoader
        db=connection.copy(alias='f5_migracion_memoria');db.settings_dict['NAME']=':memory:'
        db.ensure_connection();connections[db.alias]=db
        try:
            loader=MigrationLoader(None);estado=loader.project_state([('financiero','0003_caja_y_anulaciones')])
            with db.cursor() as cur:
                for tabla,columna in [('usuario','id_usuario'),('pago','id_pago'),('ingreso','id_ingreso'),('egreso','id_egreso'),('categoria_egreso','id_categoria_egreso')]:
                    cur.execute(f'CREATE TABLE {tabla} ({columna} bigint PRIMARY KEY)');cur.execute(f'INSERT INTO {tabla} VALUES (1)')
            with db.schema_editor(atomic=False) as editor:
                editor.create_model(estado.apps.get_model('financiero','Caja'))
                editor.create_model(estado.apps.get_model('financiero','MovimientoCaja'))
            with db.cursor() as cur:
                cur.execute('''INSERT INTO caja (id,operador_id,clave,fecha_apertura,fondo_inicial,observaciones,
                    estado,fecha_cierre,efectivo_contado,efectivo_esperado,diferencia,observaciones_cierre,cierre)
                    VALUES (1,1,%s,'2026-01-01 08:00:00',10,'Original','CERRADA','2026-01-01 17:00:00',30,30,0,'Sin diferencia','{"historica":true}')''',[uuid.uuid4().hex])
                cur.execute('''INSERT INTO movimiento_caja (id,caja_id,pago_id,fecha,operador_id,metodo,importe,referencia)
                    VALUES (1,1,1,'2026-01-01 09:00:00',1,'EFECTIVO',20,'Original')''')
                cur.execute('SELECT * FROM caja');original=cur.fetchall()
            for op in loader.disk_migrations['financiero','0004_ingresos_egresos_institucionales'].operations:
                siguiente=estado.clone();op.state_forwards('financiero',siguiente)
                with db.schema_editor(atomic=False) as editor:op.database_forwards('financiero',editor,estado,siguiente)
                estado=siguiente
            with db.cursor() as cur:
                cur.execute('SELECT * FROM caja');self.assertEqual(cur.fetchall(),original)
                cur.execute('SELECT pago_id,ingreso_id,egreso_id,importe,referencia FROM movimiento_caja')
                self.assertEqual(cur.fetchone(),(1,None,None,20,'Original'))
                for tabla in ('usuario','pago','ingreso','egreso','categoria_egreso'):
                    cur.execute(f'SELECT * FROM {tabla}');self.assertEqual(cur.fetchall(),[(1,)])
        finally:
            db.close();del connections[db.alias]

    def test_admin_rol_no_financiero_superusuario_no_consulta_operaciones(self):
        request=RequestFactory().get('/admin/');request.user=self.docente
        request.user.is_staff=True;request.user.is_superuser=True
        for modelo in (Ingreso,Egreso,CategoriaIngreso,CategoriaEgreso):
            self.assertFalse(admin.site._registry[modelo].has_view_permission(request))
