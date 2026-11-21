"""F4: dinero ficticio, SQLite en memoria, sin fondos ni datos reales."""
import csv
import importlib
import io
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models.query import QuerySet
from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from academico.flujo import matricular
from core.models import Usuario
from . import caja, anulaciones, convenios
from .consultas import importes, solvente
from .models import (Caja, MovimientoCaja, SolicitudAnulacion, Pago, Obligacion, DetallePago,
                     AplicacionPagoCuota, ConvenioPago, CuotaConvenio, ConvenioObligacion)
from .servicios import registrar_pago, reservar_recibo


class CajaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from academico.test_flujo import FlujoAcademicoTests
        FlujoAcademicoTests.setUpTestData.__func__(cls)
        cls.admin = Usuario.objects.create_user('caja-admin', 'caja-admin@example.test', 'ficticia',
            rol='ADMINISTRADOR', is_staff=True, is_superuser=True)
        cls.otra = Usuario.objects.create_user('caja-otra', 'caja-otra@example.test', 'ficticia', rol='SECRETARIA')

    def setUp(self):
        self.matricula = matricular(estudiante=self.estudiante, ciclo=self.ciclo,
            numero_matricula='CAJA-1', fecha_matricula=date(2026, 1, 2))[0]
        self.obligaciones = list(self.matricula.obligaciones.order_by('pk'))
        self.mensualidad = next(o for o in self.obligaciones if o.concepto.permite_abonos)
        self.caja = caja.abrir(usuario=self.secretaria, clave=uuid.uuid4(), fondo='10.00')
        self.client.force_login(self.secretaria)

    def pagar(self, monto='20.00', **cambios):
        return registrar_pago(**(dict(usuario=self.secretaria, estudiante=self.estudiante,
            token=reservar_recibo(self.secretaria, self.estudiante), metodo='EFECTIVO', referencia='ref-caja',
            aplicaciones=[(self.mensualidad.pk, Decimal(monto))]) | cambios))[0]

    def solicitar(self, pago=None, **cambios):
        pago = pago or self.pagar()
        return anulaciones.solicitar(**(dict(usuario=self.secretaria, pago_id=pago.pk,
            motivo='Error ficticio de registro', clave=uuid.uuid4()) | cambios))

    def aprobar(self, s, **cambios):
        revision = anulaciones.previsualizar(usuario=self.directora, solicitud_id=s.pk)
        return anulaciones.resolver(**(dict(usuario=self.directora, solicitud_id=s.pk,
            decision='APROBADA', revision=revision) | cambios))

    def cerrar(self, contado='10.00', **cambios):
        datos = dict(usuario=self.secretaria, caja_id=self.caja.pk, contado=contado, observaciones='Arqueo ficticio') | cambios
        _, revision = caja.preparar_cierre(**datos)
        return caja.cerrar(**datos, revision=revision)

    def convenio(self):
        cuotas = [{'fecha': str(timezone.localdate() + timedelta(days=10)), 'monto': '120.00'}]
        ids = [o.pk for o in self.obligaciones]
        s = convenios.solicitar(usuario=self.secretaria, estudiante_id=self.estudiante.pk,
            obligaciones=ids, cuotas=cuotas, justificacion='Ficticio', clave=uuid.uuid4())
        _, revision = convenios.previsualizar(usuario=self.directora, solicitud_id=s.pk, obligaciones=ids, cuotas=cuotas)
        return convenios.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA',
            obligaciones=ids, cuotas=cuotas, revision=revision).convenio

    def abonar(self, c, total=True):
        cuota = c.cuotas.get()
        return convenios.registrar_abono(usuario=self.secretaria, convenio_id=c.pk,
            token=reservar_recibo(self.secretaria, self.estudiante), metodo='EFECTIVO', referencia='convenio-ficticio',
            cuotas=[(cuota.pk, Decimal('120' if total else '20'))],
            obligaciones=[(o.pk, Decimal('20')) for o in (self.obligaciones if total else self.obligaciones[:1])])[0]

    def test_apertura_idempotencia_y_duplicada(self):
        c = self.caja
        self.assertEqual(caja.abrir(usuario=self.secretaria, clave=c.clave, fondo='10.00').pk, c.pk)
        with self.assertRaises(ValidationError):
            caja.abrir(usuario=self.secretaria, clave=uuid.uuid4(), fondo='0')
        with self.assertRaises(ValidationError):
            caja.abrir(usuario=self.secretaria, clave=c.clave, fondo='11')
        otra = caja.abrir(usuario=self.admin, clave=uuid.uuid4(), fondo='0')
        self.assertNotEqual(otra.pk, c.pk)

    def test_apertura_requiere_rol_actual_y_cuenta_activa(self):
        for actor in (self.directora, self.docente):
            with self.assertRaises(PermissionDenied):
                caja.abrir(usuario=actor, clave=uuid.uuid4(), fondo='0')
        Usuario.objects.filter(pk=self.admin.pk).update(estado_cuenta='INACTIVA')
        with self.assertRaises(PermissionDenied):
            caja.abrir(usuario=self.admin, clave=uuid.uuid4(), fondo='0')

    def test_importes_invalidos_apertura(self):
        for valor in ('-1', 'NaN', 'Infinity', '0.001', '99999999999999999999', 'texto'):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                caja.abrir(usuario=self.admin, clave=uuid.uuid4(), fondo=valor)

    def test_caja_abierta_unica_restriccion_bd(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Caja.objects.create(operador=self.secretaria, clave=uuid.uuid4(), fondo_inicial=0)

    def test_cobro_requiere_caja_propia_abierta_sin_cambios_parciales(self):
        self.cerrar()
        with self.assertRaisesMessage(ValidationError, 'Abra su caja'):
            self.pagar()
        self.assertFalse(Pago.objects.exists())
        caja.abrir(usuario=self.admin, clave=uuid.uuid4(), fondo='0')
        with self.assertRaises(ValidationError):
            self.pagar()

    def test_pago_movimiento_atomico_y_reenvio_no_duplica(self):
        token = reservar_recibo(self.secretaria, self.estudiante)
        p = self.pagar(token=token)
        self.assertEqual(self.pagar(token=token).pk, p.pk)
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        m = p.movimiento_caja
        self.assertEqual((m.caja_id, m.operador_id, m.metodo, m.importe),
                         (self.caja.pk, self.secretaria.pk, 'EFECTIVO', Decimal('20')))

    def test_movimiento_unico_restriccion_bd(self):
        p = self.pagar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovimientoCaja.objects.create(caja=self.caja, pago=p, operador=self.secretaria,
                metodo=p.metodo_pago, importe=p.monto_total, referencia=p.referencia)

    def test_cash_transfer_separados_y_sin_contabilizar_dos_veces(self):
        self.pagar('5')
        self.pagar('7', metodo='TRANSFERENCIA')
        t = caja.totales(self.caja)
        self.assertEqual(Decimal(t['efectivo_vigente']), 5)
        self.assertEqual(Decimal(t['transferencias_vigentes']), 7)
        self.assertEqual(Decimal(t['esperado']), 15)
        self.assertEqual(Decimal(t['ingresos_vigentes']), 12)
        self.assertEqual(t['recibos'], 2)

    def test_fallo_movimiento_revierte_pago_y_aplicaciones(self):
        with patch.object(MovimientoCaja, 'save', side_effect=DatabaseError('Ficticio')), self.assertRaises(DatabaseError):
            self.pagar()
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(DetallePago.objects.exists())
        self.assertEqual(importes(self.mensualidad)[2], 20)

    def test_apertura_nueva_mismo_dia_tras_cerrar(self):
        self.cerrar()
        nueva = caja.abrir(usuario=self.secretaria, clave=uuid.uuid4(), fondo='0')
        self.assertNotEqual(nueva.pk, self.caja.pk)

    def test_cierre_cuadrado_y_reintento(self):
        self.pagar()
        datos = dict(usuario=self.secretaria, caja_id=self.caja.pk, contado='30.00', observaciones='Cuadrado')
        _, revision = caja.preparar_cierre(**datos)
        c = caja.cerrar(**datos, revision=revision)
        self.assertEqual(c.diferencia, 0)
        self.assertEqual(caja.cerrar(**datos, revision=revision).pk, c.pk)
        with self.assertRaises(ValidationError):
            caja.cerrar(**(datos | {'contado': '31'}), revision=revision)

    def test_arqueo_faltante(self):
        self.assertEqual(self.cerrar('8').diferencia, -2)

    def test_arqueo_sobrante(self):
        self.assertEqual(self.cerrar('12').diferencia, 2)

    def test_cierre_caja_ajena_denegado(self):
        for actor in (self.admin, self.otra):
            with self.assertRaises(PermissionDenied):
                caja.preparar_cierre(usuario=actor, caja_id=self.caja.pk, contado='10')
        with self.assertRaises(PermissionDenied):
            caja.preparar_cierre(usuario=self.directora, caja_id=self.caja.pk, contado='10')

    def test_cierre_rechaza_movimientos_despues_comparacion(self):
        _, revision = caja.preparar_cierre(usuario=self.secretaria, caja_id=self.caja.pk, contado='10')
        self.pagar()
        with self.assertRaisesMessage(ValidationError, 'Hubo movimientos'):
            caja.cerrar(usuario=self.secretaria, caja_id=self.caja.pk, contado='10', revision=revision)
        self.caja.refresh_from_db()
        self.assertEqual(self.caja.estado, 'ABIERTA')

    def test_cierre_firma_alterada_y_ajena(self):
        _, revision = caja.preparar_cierre(usuario=self.secretaria, caja_id=self.caja.pk, contado='10')
        with self.assertRaises(ValidationError):
            caja.cerrar(usuario=self.secretaria, caja_id=self.caja.pk, contado='11', revision=revision)
        with self.assertRaises(ValidationError):
            caja.cerrar(usuario=self.secretaria, caja_id=self.caja.pk, contado='10', revision='alterado')

    def test_cierre_inmutable_y_movimiento_no_editable(self):
        p = self.pagar()
        c = self.cerrar('30')
        foto = c.cierre
        with self.assertRaises(ValidationError):
            c.save()
        with self.assertRaises(ValidationError):
            c.delete()
        with self.assertRaises(ValidationError):
            p.movimiento_caja.save()
        with self.assertRaises(ValidationError):
            p.movimiento_caja.delete()
        c.refresh_from_db()
        self.assertEqual(c.cierre, foto)

    def test_fallo_cierre_no_conserva_fotografia_parcial(self):
        original = Caja.save
        def fallar(obj, *args, **kwargs):
            original(obj, *args, **kwargs)
            raise DatabaseError('Ficticio')
        with patch.object(Caja, 'save', fallar), self.assertRaises(DatabaseError):
            self.cerrar()
        self.caja.refresh_from_db()
        self.assertEqual(self.caja.estado, 'ABIERTA')
        self.assertEqual(self.caja.cierre, {})

    def test_solicitud_no_modifica_saldos_ni_movimientos(self):
        p = self.pagar()
        antes = (list(Pago.objects.values()), list(DetallePago.objects.values()), list(Obligacion.objects.values()), caja.totales(self.caja))
        s = self.solicitar(p)
        self.assertEqual(s.estado, 'PENDIENTE')
        self.assertEqual(antes, (list(Pago.objects.values()), list(DetallePago.objects.values()), list(Obligacion.objects.values()), caja.totales(self.caja)))

    def test_solicitud_motivo_y_permisos(self):
        p = self.pagar()
        with self.assertRaises(ValidationError):
            self.solicitar(p, motivo='  ')
        for actor in (self.directora, self.admin, self.docente):
            with self.assertRaises(PermissionDenied):
                self.solicitar(p, usuario=actor)
        self.assertFalse(SolicitudAnulacion.objects.exists())

    def test_solicitudes_duplicadas_idempotencia_y_clave_ajena(self):
        p = self.pagar()
        s = self.solicitar(p)
        self.assertEqual(self.solicitar(p, clave=s.clave).pk, s.pk)
        with self.assertRaises(ValidationError):
            self.solicitar(p)
        with self.assertRaises(ValidationError):
            self.solicitar(p, clave=s.clave, motivo='Otro')
        with self.assertRaises(ValidationError):
            self.solicitar(p, usuario=self.otra, clave=s.clave)

    def test_solicitud_pendiente_restriccion_bd(self):
        s = self.solicitar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SolicitudAnulacion.objects.create(clave=uuid.uuid4(), pago=s.pago, solicitante=self.secretaria,
                motivo='Duplicada', anteriores={})

    def test_anulacion_restablece_saldo_sin_alterar_originales(self):
        p = self.pagar()
        antes = Pago.objects.values().get(pk=p.pk)
        detalles = list(DetallePago.objects.values())
        s = self.aprobar(self.solicitar(p))
        despues = Pago.objects.values().get(pk=p.pk)
        self.assertEqual(antes | {'estado': 'ANULADO'}, despues)
        self.assertEqual(detalles, list(DetallePago.objects.values()))
        self.assertEqual(importes(self.mensualidad)[2], 20)
        self.assertEqual(s.directora_id, self.directora.pk)
        self.assertIsNotNone(s.fecha_resolucion)
        self.assertFalse(s.aplicados['devolucion'])

    def test_solvencia_vuelve_insolvente_al_anular_pago(self):
        p = self.pagar('120', aplicaciones=[(o.pk, Decimal('20')) for o in self.obligaciones])
        self.assertTrue(solvente(self.estudiante))
        s = self.aprobar(self.solicitar(p))
        self.assertFalse(solvente(self.estudiante))
        self.assertFalse(s.aplicados['solvente'])

    def test_no_modifica_otros_pagos(self):
        p = self.pagar('5')
        otro = self.pagar('7')
        s = self.solicitar(p)
        self.aprobar(s)
        otro.refresh_from_db()
        self.assertEqual(otro.estado, 'REGISTRADO')
        self.assertEqual(importes(self.mensualidad)[2], 13)

    def test_efectivo_anulado_permanece_en_arqueo_fisico(self):
        s = self.aprobar(self.solicitar())
        t = caja.totales(self.caja)
        self.assertEqual(Decimal(t['efectivo_vigente']), 0)
        self.assertEqual(Decimal(t['efectivo_anulado_retenido']), 20)
        self.assertEqual(Decimal(t['esperado']), 30)
        self.assertEqual(self.cerrar('30').diferencia, 0)

    def test_transferencia_anulada_no_modifica_efectivo(self):
        self.aprobar(self.solicitar(self.pagar(metodo='TRANSFERENCIA')))
        t = caja.totales(self.caja)
        self.assertEqual(Decimal(t['transferencias_vigentes']), 0)
        self.assertEqual(Decimal(t['anulados']), 20)
        self.assertEqual(Decimal(t['esperado']), 10)

    def test_rechazo_con_motivo_sin_cambio_financiero(self):
        s = self.solicitar()
        antes = (list(Pago.objects.values()), list(Obligacion.objects.values()), caja.totales(self.caja))
        with self.assertRaises(ValidationError):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='RECHAZADA')
        anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='RECHAZADA', observaciones='No procede')
        self.assertEqual(antes, (list(Pago.objects.values()), list(Obligacion.objects.values()), caja.totales(self.caja)))

    def test_solo_directora_activa_autoriza_incluso_superusuario_denegado(self):
        s = self.solicitar()
        for actor in (self.admin, self.secretaria, self.docente):
            with self.assertRaises(PermissionDenied):
                self.aprobar(s, usuario=actor)
        Usuario.objects.filter(pk=self.directora.pk).update(rol='ADMINISTRADOR')
        with self.assertRaises(PermissionDenied):
            self.aprobar(s)
        self.assertEqual(Pago.objects.get(pk=s.pago_id).estado, 'REGISTRADO')

    def test_solicitante_sin_permiso_invalida_aprobacion_permite_rechazar(self):
        s = self.solicitar()
        Usuario.objects.filter(pk=self.secretaria.pk).update(estado_cuenta='INACTIVA')
        with self.assertRaises(ValidationError):
            self.aprobar(s)
        anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='RECHAZADA', observaciones='Cuenta inactiva')

    def test_aprobacion_repetida_y_contradictoria(self):
        s = self.solicitar()
        self.aprobar(s)
        self.assertEqual(anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA').pk, s.pk)
        with self.assertRaises(ValidationError):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='RECHAZADA', observaciones='Cambiar')
        with self.assertRaises(ValidationError):
            self.solicitar(s.pago)
        self.assertEqual(MovimientoCaja.objects.count(), 1)

    def test_rechazo_repetido_y_nueva_solicitud_permitida(self):
        s = self.solicitar()
        for _ in range(2):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='RECHAZADA', observaciones='No procede')
        nueva = self.solicitar(s.pago)
        self.assertNotEqual(nueva.pk, s.pk)

    def test_caja_cerrada_bloquea_solicitar_y_aprobar_sin_cambiar_foto(self):
        p = self.pagar()
        s = self.solicitar(p)
        c = self.cerrar('30')
        antes = c.cierre
        with self.assertRaisesMessage(ValidationError, 'cerrada'):
            self.aprobar(s)
        with self.assertRaises(ValidationError):
            self.solicitar(p, clave=uuid.uuid4())
        c.refresh_from_db()
        self.assertEqual(c.cierre, antes)
        self.assertEqual(Pago.objects.get(pk=p.pk).estado, 'REGISTRADO')
        anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='RECHAZADA', observaciones='Caja cerrada')

    def test_pago_historico_sin_caja_bloqueado(self):
        p = Pago.objects.create(numero_recibo='LEGADO', estudiante=self.estudiante, usuario=self.secretaria,
            fecha_pago=timezone.now(), monto_total='20', metodo_pago='EFECTIVO', estado='REGISTRADO')
        with self.assertRaisesMessage(ValidationError, 'histórico sin caja'):
            self.solicitar(p)

    def test_datos_obsoletos_pago_posterior_bloquea_aprobacion(self):
        p = self.pagar('5')
        s = self.solicitar(p)
        self.pagar('7')
        with self.assertRaisesMessage(ValidationError, 'cambiaron'):
            self.aprobar(s)
        p.refresh_from_db()
        self.assertEqual(p.estado, 'REGISTRADO')

    def test_obligacion_anulada_bloquea_aprobacion(self):
        s = self.solicitar()
        Obligacion.objects.filter(pk=self.mensualidad.pk).update(estado='ANULADA')
        with self.assertRaises(ValidationError):
            self.aprobar(s)

    def test_aprobacion_necesita_comparacion_firmada_y_rechaza_saldos_cambiados(self):
        s = self.solicitar()
        with self.assertRaises(ValidationError):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA')
        revision = anulaciones.previsualizar(usuario=self.directora, solicitud_id=s.pk)
        Obligacion.objects.filter(pk=self.mensualidad.pk).update(monto_original=25)
        with self.assertRaises(ValidationError):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA', revision=revision)

    def test_rollback_anulacion_despues_modificar_pago(self):
        s = self.solicitar()
        revision = anulaciones.previsualizar(usuario=self.directora, solicitud_id=s.pk)
        with patch.object(Obligacion, 'actualizar_estado', side_effect=DatabaseError('Ficticio')), self.assertRaises(DatabaseError):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA', revision=revision)
        s.refresh_from_db()
        s.pago.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')
        self.assertEqual(s.pago.estado, 'REGISTRADO')
        self.assertEqual(importes(self.mensualidad)[2], 0)

    def test_rollback_resolucion_despues_escritura(self):
        s = self.solicitar()
        revision = anulaciones.previsualizar(usuario=self.directora, solicitud_id=s.pk)
        original = SolicitudAnulacion.save
        def fallar(obj, *args, **kwargs):
            original(obj, *args, **kwargs)
            raise DatabaseError('Ficticio')
        with patch.object(SolicitudAnulacion, 'save', fallar), self.assertRaises(DatabaseError):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA', revision=revision)
        self.assertEqual(SolicitudAnulacion.objects.get(pk=s.pk).estado, 'PENDIENTE')
        self.assertEqual(Pago.objects.get(pk=s.pago_id).estado, 'REGISTRADO')

    def test_historial_inmutable_y_sin_eliminacion(self):
        s = self.solicitar()
        with self.assertRaises(ValidationError):
            s.delete()
        s.motivo = 'Alterado'
        with self.assertRaises(ValidationError):
            s.save()
        s.refresh_from_db()
        s = self.aprobar(s)
        with self.assertRaises(ValidationError):
            s.save()

    def test_convenio_cumplido_reactivado_cuotas_y_originales_restablecidos(self):
        c = self.convenio()
        p = self.abonar(c)
        c.refresh_from_db()
        self.assertEqual(c.estado, 'CUMPLIDO')
        aplicaciones = list(AplicacionPagoCuota.objects.values())
        detalles = list(DetallePago.objects.values())
        self.aprobar(self.solicitar(p))
        c.refresh_from_db()
        self.assertEqual(c.estado, 'ACTIVO')
        self.assertEqual(c.cuotas.get().estado, 'PENDIENTE')
        self.assertEqual(convenios.resumen(c)['saldo'], 120)
        self.assertEqual(sum(importes(o)[2] for o in self.obligaciones), 120)
        self.assertEqual(list(AplicacionPagoCuota.objects.values()), aplicaciones)
        self.assertEqual(list(DetallePago.objects.values()), detalles)

    def test_convenio_parcial_restaurado_y_otro_pago_conservado(self):
        c = self.convenio()
        p = self.abonar(c, total=False)
        cuota = c.cuotas.get()
        otro = convenios.registrar_abono(usuario=self.secretaria, convenio_id=c.pk,
            token=reservar_recibo(self.secretaria, self.estudiante), metodo='TRANSFERENCIA', referencia='',
            cuotas=[(cuota.pk, Decimal('20'))], obligaciones=[(self.obligaciones[1].pk, Decimal('20'))])[0]
        self.aprobar(self.solicitar(p))
        self.assertEqual(convenios.resumen(c)['saldo'], 100)
        otro.refresh_from_db()
        self.assertEqual(otro.estado, 'REGISTRADO')
        self.assertEqual(MovimientoCaja.objects.count(), 2)

    def test_convenio_incumplido_conserva_estado(self):
        c = self.convenio()
        p = self.abonar(c, total=False)
        ConvenioPago.objects.filter(pk=c.pk).update(estado='INCUMPLIDO')
        self.aprobar(self.solicitar(p))
        c.refresh_from_db()
        self.assertEqual(c.estado, 'INCUMPLIDO')
        self.assertFalse(solvente(self.estudiante))

    def test_anular_convenio_restaura_insolvencia_cuota_vencida(self):
        c = self.convenio()
        CuotaConvenio.objects.filter(convenio=c).update(fecha_vencimiento=timezone.localdate()-timedelta(days=1))
        p = self.abonar(c)
        self.assertTrue(solvente(self.estudiante))
        self.aprobar(self.solicitar(p))
        self.assertFalse(solvente(self.estudiante))

    def test_cobro_convenio_sin_caja_bloqueado(self):
        c = self.convenio()
        self.cerrar()
        with self.assertRaisesMessage(ValidationError, 'Abra su caja'):
            self.abonar(c)
        self.assertFalse(Pago.objects.exists())

    def test_fallo_movimiento_convenio_revierte_todo(self):
        c = self.convenio()
        with patch.object(MovimientoCaja, 'save', side_effect=DatabaseError('Ficticio')), self.assertRaises(DatabaseError):
            self.abonar(c)
        c.refresh_from_db()
        self.assertEqual(c.estado, 'ACTIVO')
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(AplicacionPagoCuota.objects.exists())
        self.assertEqual(convenios.resumen(c)['saldo'], 120)

    def test_fallo_cuota_anulacion_revierte_pago_saldo_e_historial(self):
        c = self.convenio()
        p = self.abonar(c)
        s = self.solicitar(p)
        revision = anulaciones.previsualizar(usuario=self.directora, solicitud_id=s.pk)
        with patch.object(CuotaConvenio, 'save', side_effect=DatabaseError('Ficticio')), self.assertRaises(DatabaseError):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA', revision=revision)
        c.refresh_from_db()
        p.refresh_from_db()
        self.assertEqual(c.estado, 'CUMPLIDO')
        self.assertEqual(p.estado, 'REGISTRADO')
        self.assertEqual(convenios.resumen(c)['saldo'], 0)

    def test_cobro_ordinario_antes_convenio_bloquea_anulacion(self):
        p = self.pagar('5')
        cuotas = [{'fecha':str(timezone.localdate()),'monto':'115'}]
        ids = [o.pk for o in self.obligaciones]
        s = convenios.solicitar(usuario=self.secretaria, estudiante_id=self.estudiante.pk,
            obligaciones=ids, cuotas=cuotas, justificacion='Ficticia', clave=uuid.uuid4())
        _, revision = convenios.previsualizar(usuario=self.directora, solicitud_id=s.pk, obligaciones=ids, cuotas=cuotas)
        convenios.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA', obligaciones=ids, cuotas=cuotas, revision=revision)
        with self.assertRaisesMessage(ValidationError, 'convenio posterior'):
            self.solicitar(p)

    def test_orden_bloqueos_cobro_y_anulacion(self):
        original = QuerySet.select_for_update
        orden = []
        def observar(qs, *args, **kwargs):
            orden.append(qs.model.__name__)
            return original(qs, *args, **kwargs)
        with patch.object(QuerySet, 'select_for_update', observar):
            p = self.pagar()
        self.assertEqual(orden[:4], ['Usuario', 'Caja', 'Estudiante', 'Obligacion'])
        s = self.solicitar(p)
        revision = anulaciones.previsualizar(usuario=self.directora, solicitud_id=s.pk)
        orden.clear()
        with patch.object(QuerySet, 'select_for_update', observar):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA', revision=revision)
        self.assertEqual(orden, ['Usuario', 'Caja', 'Estudiante', 'Obligacion', 'ConvenioPago', 'CuotaConvenio', 'Pago', 'SolicitudAnulacion'])

    def test_rutas_protegidas_y_solo_caja_propia_secretaria(self):
        p = self.pagar()
        s = self.solicitar(p)
        lectura = [reverse('caja_listado'), reverse('caja_detalle', args=[self.caja.pk]),
            reverse('anulaciones_listado'), reverse('anulaciones_detalle', args=[s.pk])]
        operaciones = [reverse('caja_apertura'), reverse('caja_cierre', args=[self.caja.pk]), reverse('anulaciones_nueva', args=[p.pk])]
        for rol in ('MAESTRO', 'ESTUDIANTE', 'PASTOR_PRINCIPAL'):
            actor = Usuario.objects.create_user('f4-'+rol, rol+'@example.test', 'ficticia', rol=rol)
            self.client.force_login(actor)
            for url in lectura + operaciones:
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.force_login(self.otra)
        self.assertEqual(self.client.get(lectura[1]).status_code, 404)
        self.assertEqual(self.client.get(operaciones[1]).status_code, 404)
        self.client.force_login(self.directora)
        for url in lectura:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse('caja_apertura')).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('anulaciones_detalle', args=[s.pk]), {'decision':'APROBADA'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('anulaciones_nueva', args=[p.pk]), {}).status_code, 403)

    def test_http_apertura_arqueo_y_confirmacion(self):
        self.cerrar()
        url = reverse('caja_apertura')
        datos = {'clave': str(uuid.uuid4()), 'fondo':'5.00', 'observaciones':'Ficticia'}
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        c = Caja.objects.get(clave=datos['clave'])
        url = reverse('caja_cierre', args=[c.pk])
        r = self.client.post(url, {'contado':'6.00', 'observaciones':'Sobrante', 'accion':'comparar'})
        self.assertContains(r, 'Confirmar cierre definitivo')
        token = r.context['form'].data['revision']
        self.assertEqual(self.client.post(url, {'contado':'6.00','observaciones':'Sobrante','revision':token,'accion':'confirmar'}).status_code, 302)
        self.assertContains(self.client.get(reverse('caja_detalle',args=[c.pk])), 'Sobrante')

    def test_http_solicitud_aprobacion_reenvio_y_recibo_auditable(self):
        p = self.pagar()
        url = reverse('anulaciones_nueva', args=[p.pk])
        d = {'clave': str(uuid.uuid4()), 'motivo':'<script>alert(1)</script>'}
        self.assertEqual(self.client.post(url, d).status_code, 302)
        s = SolicitudAnulacion.objects.get()
        url = reverse('anulaciones_detalle', args=[s.pk])
        self.client.force_login(self.directora)
        r = self.client.post(url, {'decision':'APROBADA', 'accion':'comparar'})
        self.assertContains(r, 'Confirmar aprobación definitiva')
        token = r.context['form'].data['revision']
        datos = {'decision':'APROBADA','revision':token,'accion':'resolver'}
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        recibo = self.client.get(reverse('finanzas_recibo', args=[p.pk]))
        self.assertContains(recibo, 'ANULADO')
        self.assertContains(recibo, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(recibo, '<script>alert(1)</script>')
        self.assertContains(recibo, self.directora.numero_usuario)

    def test_http_rechazo_sin_motivo_y_csrf(self):
        s = self.solicitar()
        self.client.force_login(self.directora)
        url = reverse('anulaciones_detalle', args=[s.pk])
        self.assertContains(self.client.post(url, {'decision':'RECHAZADA'}), 'Explique el rechazo')
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.directora)
        self.assertEqual(c.post(url, {'decision':'APROBADA'}).status_code, 403)

    def test_busqueda_fechas_referencia_y_filtro_operador_no_elude_permisos(self):
        p = self.pagar()
        url = reverse('anulaciones_listado')
        for consulta in (p.numero_recibo, self.estudiante.codigo_estudiante, 'ref-caja'):
            self.assertContains(self.client.get(url, {'q':consulta}), p.numero_recibo)
        manana = str(timezone.localdate()+timedelta(days=1))
        self.assertNotContains(self.client.get(url, {'desde':manana}), p.numero_recibo)
        self.assertContains(self.client.get(url, {'desde':'invalida'}), 'fecha válida')
        otra = caja.abrir(usuario=self.otra, clave=uuid.uuid4(), fondo='0')
        r = self.client.get(reverse('caja_listado'), {'operador':self.otra.pk})
        self.assertNotContains(r, f'Caja #{otra.pk} ·')

    def test_reportes_csv_y_fotografia_imprimible(self):
        self.pagar(referencia='=SUM(1,1)')
        self.cerrar('30')
        self.client.force_login(self.directora)
        r = self.client.get(reverse('caja_detalle', args=[self.caja.pk]), {'formato':'csv'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/csv; charset=utf-8')
        filas = list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
        self.assertEqual(filas[1][-1], "'=SUM(1,1)")
        r = self.client.get(reverse('caja_listado'), {'estado':'CERRADA', 'formato':'csv'})
        self.assertIn(b'cajas.csv', r['Content-Disposition'].encode())
        self.assertContains(self.client.get(reverse('caja_detalle', args=[self.caja.pk])), 'Fotografía inmutable')

    def test_admin_no_elude_servicios(self):
        for modelo in (Caja, MovimientoCaja, SolicitudAnulacion):
            self.assertNotIn(modelo, admin.site._registry)
        request = RequestFactory().get('/admin/')
        request.user = self.admin
        pago_admin = admin.site._registry[Pago]
        self.assertFalse(pago_admin.has_add_permission(request))
        self.assertFalse(pago_admin.has_change_permission(request))
        self.assertFalse(pago_admin.has_delete_permission(request))
        for modelo in (ConvenioPago, AplicacionPagoCuota):
            self.assertFalse(admin.site._registry[modelo].has_change_permission(request))

    def test_migracion_solo_tablas_nuevas_y_esquema_creado(self):
        m = importlib.import_module('financiero.migrations.0003_caja_y_anulaciones')
        permitidas = {'Caja','MovimientoCaja','SolicitudAnulacion'}
        for operacion in m.Migration.operations:
            nombre = getattr(operacion, 'model_name', None) or getattr(operacion, 'name', None)
            self.assertIn(nombre.lower(), {n.lower() for n in permitidas})
        with connection.cursor() as cursor:
            tablas = set(connection.introspection.table_names(cursor))
        self.assertTrue({'caja','movimiento_caja','solicitud_anulacion'} <= tablas)
        self.assertTrue(connection.settings_dict['NAME'].startswith('file:memorydb'))

    def test_recibo_anulado_no_puede_reutilizar_reserva_ni_numero(self):
        token = reservar_recibo(self.secretaria, self.estudiante)
        p = self.pagar(token=token)
        self.aprobar(self.solicitar(p))
        with self.assertRaises(ValidationError):
            self.pagar(token=token)
        nuevo = self.pagar()
        self.assertNotEqual(p.numero_recibo, nuevo.numero_recibo)
        self.assertEqual(Pago.objects.count(), 2)

    def test_error_solvencia_revierte_anulacion_entera(self):
        s = self.solicitar()
        revision = anulaciones.previsualizar(usuario=self.directora, solicitud_id=s.pk)
        with patch('financiero.anulaciones.solvente', side_effect=DatabaseError('Ficticio')), self.assertRaises(DatabaseError):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA', revision=revision)
        self.assertEqual(Pago.objects.get(pk=s.pago_id).estado, 'REGISTRADO')
        self.assertEqual(SolicitudAnulacion.objects.get(pk=s.pk).estado, 'PENDIENTE')

    def test_directora_inactiva_y_rol_revocado_no_autorizan_http_ni_servicio(self):
        s = self.solicitar()
        revision = anulaciones.previsualizar(usuario=self.directora, solicitud_id=s.pk)
        Usuario.objects.filter(pk=self.directora.pk).update(estado_cuenta='INACTIVA')
        with self.assertRaises(PermissionDenied):
            anulaciones.resolver(usuario=self.directora, solicitud_id=s.pk, decision='APROBADA', revision=revision)
        self.directora.refresh_from_db()
        self.client.force_login(self.directora)
        self.assertIn(self.client.post(reverse('anulaciones_detalle',args=[s.pk]), {'decision':'APROBADA'}).status_code, (302,403))

    def test_parametros_manipulados_no_cambian_operador_ni_directora(self):
        self.cerrar()
        r = self.client.post(reverse('caja_apertura'), {'clave':str(uuid.uuid4()),'fondo':'0', 'operador':self.otra.pk})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Caja.objects.filter(operador=self.secretaria,estado='ABIERTA').exists())
        self.assertFalse(Caja.objects.filter(operador=self.otra).exists())
        s = self.solicitar()
        self.client.force_login(self.directora)
        url = reverse('anulaciones_detalle',args=[s.pk])
        self.assertEqual(self.client.post(url, {'decision':'RECHAZADA','observaciones':'No procede','directora':self.admin.pk}).status_code,302)
        s.refresh_from_db()
        self.assertEqual(s.directora_id,self.directora.pk)

    def test_reportes_financieros_excluyen_anulados(self):
        from reportes.consultas import generar
        p = self.pagar()
        self.aprobar(self.solicitar(p))
        self.client.force_login(self.directora)
        r = self.client.get(reverse('reportes_consultar',args=['pagos']))
        self.assertEqual(r.status_code,200)
        self.assertNotContains(r, p.numero_recibo)

    def test_saldos_excedentes_bloquean_anular_convenio(self):
        from .models import Donante, Donacion
        c = self.convenio()
        p = self.abonar(c)
        donante = Donante.objects.create(nombre_completo='Ficticio F4',tipo='PERSONA',es_anonimo=True,
            estado='ACTIVO',fecha_registro=timezone.now(),fecha_actualizacion=timezone.now())
        Donacion.objects.create(donante=donante,obligacion=self.obligaciones[0],usuario_registra=self.secretaria,
            fecha_compromiso=timezone.localdate(),fecha_registro=timezone.now(),fecha_actualizacion=timezone.now(),monto='5',estado='RECIBIDA')
        with self.assertRaisesMessage(ValidationError,'excedentes'):
            self.solicitar(p)
        p.refresh_from_db()
        self.assertEqual(p.estado,'REGISTRADO')
