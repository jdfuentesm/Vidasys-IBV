"""Pruebas indispensables del recorrido financiero. Solo SQLite aislado."""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academico import test_flujo as fixtures
from academico.flujo import matricular
from academico.models import Matricula, InscripcionCurso, Maestro
from core.models import Usuario
from .calendario import guardar, leer, ruta
from .consultas import importes, solvente
from .models import (Obligacion, ConceptoCobro, Pago, DetallePago, ConvenioPago, ConvenioObligacion,
                     CuotaConvenio, AplicacionPagoCuota, Donante, Donacion)
from .servicios import registrar_pago, reservar_recibo


class FinancieroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.FlujoAcademicoTests.setUpTestData()
        b = fixtures.FlujoAcademicoTests
        cls.estudiante, cls.ciclo, cls.secretaria, cls.directora = b.estudiante, b.ciclo, b.secretaria, b.directora
        cls.docente, cls.maestro = b.docente, b.maestro
        cls.admin = Usuario.objects.create_user('admin-fin', 'admin-fin@example.test', 'ficticia', rol='ADMINISTRADOR')

    def matricula(self, estudiante=None):
        return matricular(estudiante=estudiante or self.estudiante, ciclo=self.ciclo,
            numero_matricula='FIN-M1', fecha_matricula=date(2026, 1, 2))[0]

    def obligacion(self):
        self.matricula()
        return Obligacion.objects.get(concepto__nombre='MENSUALIDAD', fecha_vencimiento='2026-02-10')

    def pagar(self, obligacion, monto='20.00', token=None, **cambios):
        return registrar_pago(**(dict(usuario=self.secretaria, estudiante=self.estudiante,
            token=token or reservar_recibo(self.secretaria, self.estudiante), metodo='EFECTIVO', referencia='',
            aplicaciones=[(obligacion.pk, Decimal(monto))]) | cambios))

    def test_seis_obligaciones_total_120_reintento_preserva_historia(self):
        docente = list(Maestro.objects.values())
        m = self.matricula()
        self.assertEqual(m.obligaciones.count(), 6)
        self.assertEqual(sum(o.monto_final for o in m.obligaciones.all()), Decimal('120.00'))
        self.assertEqual(list(m.obligaciones.filter(concepto__nombre='MENSUALIDAD').order_by('fecha_vencimiento').values_list('fecha_vencimiento', flat=True)),
            [date(2026, n, 10) for n in range(2, 7)])
        primera = m.obligaciones.first()
        Obligacion.objects.filter(pk=primera.pk).update(estado='ANULADA', monto_descuento='5.00')
        antes = (list(Obligacion.objects.values()), list(InscripcionCurso.objects.values()))
        self.matricula()
        self.assertEqual(antes, (list(Obligacion.objects.values()), list(InscripcionCurso.objects.values())))
        self.assertEqual(list(Maestro.objects.values()), docente)

    def test_fallo_generacion_revierte_matricula_inscripciones_y_obligaciones(self):
        original = Obligacion.save
        contador = [0]
        def fallar(o, *args, **kwargs):
            contador[0] += 1
            if contador[0] == 3:
                raise DatabaseError('Fallo ficticio')
            return original(o, *args, **kwargs)
        with patch.object(Obligacion, 'save', fallar), self.assertRaises(DatabaseError):
            self.matricula()
        self.assertFalse(Matricula.objects.exists())
        self.assertFalse(InscripcionCurso.objects.exists())
        self.assertFalse(Obligacion.objects.exists())

    def test_calendario_valida_fechas_y_faltante_impide_alta_parcial(self):
        datos = leer(self.ciclo)
        for cambios in ({'meses': ['2026-02']*5}, {'meses': ['2027-02','2027-03','2027-04','2027-05','2027-06']}, {'matricula':'2025-12-01'}):
            with self.assertRaises(ValidationError):
                guardar(self.ciclo, datos | cambios)
        ruta(self.ciclo).unlink()
        try:
            with self.assertRaises(ValidationError):
                self.matricula()
            self.assertFalse(Matricula.objects.exists())
        finally:
            guardar(self.ciclo, datos)
        self.matricula()
        with self.assertRaises(ValidationError):
            guardar(self.ciclo, datos)

    def test_pago_saldo_abonos_anulados_y_donaciones_recibidas(self):
        o = self.obligacion()
        self.pagar(o, '5.00')
        self.assertEqual(importes(o), (Decimal('5'), Decimal('0'), Decimal('15')))
        pago, _ = self.pagar(o, '3.00')
        Pago.objects.filter(pk=pago.pk).update(estado='ANULADO')
        donante = Donante.objects.create(nombre_completo='Donante ficticio', tipo='PERSONA', es_anonimo=True, estado='ACTIVO', fecha_registro=timezone.now(), fecha_actualizacion=timezone.now())
        base = dict(donante=donante, obligacion=o, usuario_registra=self.secretaria, fecha_compromiso=date(2026,1,1),
                    fecha_registro=timezone.now(), fecha_actualizacion=timezone.now())
        Donacion.objects.create(**base, monto='4.00', estado='RECIBIDA')
        Donacion.objects.create(**base, monto='9.00', estado='COMPROMETIDA')
        self.assertEqual(importes(o), (Decimal('5'), Decimal('4'), Decimal('11')))
        self.pagar(o, '11.00')
        o.refresh_from_db()
        self.assertEqual(o.estado, 'PAGADA')
        self.assertEqual(importes(o)[2], Decimal('0'))

    def test_abono_no_permitido_excedente_cero_negativo_no_guardan(self):
        o = self.obligacion()
        ConceptoCobro.objects.filter(pk=o.concepto_id).update(permite_abonos=False)
        for monto in ('5.00','20.01','0.00','-1.00','0.001'):
            with self.subTest(monto=monto), self.assertRaises(ValidationError):
                self.pagar(o, monto)
        self.assertFalse(Pago.objects.exists())
        self.pagar(o)
        with self.assertRaises(ValidationError):
            self.pagar(o, '1.00')
        self.assertEqual(Pago.objects.count(), 1)

    def test_recibos_unicos_correlativos_y_reenvio_no_duplica(self):
        o = self.obligacion()
        token = reservar_recibo(self.secretaria, self.estudiante)
        p1, creado = self.pagar(o, '2.00', token=token)
        self.assertTrue(creado)
        p2, creado = self.pagar(o, '2.00', token=token)
        self.assertFalse(creado)
        self.assertEqual(p1.pk, p2.pk)
        with self.assertRaises(ValidationError):
            self.pagar(o, '3.00', token=token)
        p3, _ = self.pagar(o, '3.00')
        self.assertGreater(p3.pk, p1.pk)
        self.assertNotEqual(p1.numero_recibo, p3.numero_recibo)
        self.assertEqual(Pago.objects.count(), 2)
        self.assertEqual(DetallePago.objects.count(), 2)

    def test_fallo_aplicacion_revierte_pago_detalles_y_estados(self):
        self.matricula()
        obligaciones = list(Obligacion.objects.filter(concepto__nombre='MENSUALIDAD')[:2])
        antes = list(Obligacion.objects.values())
        original = DetallePago.save
        contador = [0]
        def fallo(detalle,*args,**kwargs):
            contador[0]+=1
            if contador[0] == 2:
                raise DatabaseError('Fallo ficticio')
            return original(detalle,*args,**kwargs)
        with patch.object(DetallePago, 'save', fallo), self.assertRaises(DatabaseError):
            self.pagar(obligaciones[0], aplicaciones=[(o.pk, Decimal('5.00')) for o in obligaciones])
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(DetallePago.objects.exists())
        self.assertEqual(list(Obligacion.objects.values()), antes)

    def test_pago_multiple_suma_aplicaciones_e_impide_obligacion_repetida(self):
        self.matricula()
        obligaciones = list(Obligacion.objects.filter(concepto__nombre='MENSUALIDAD')[:2])
        with self.assertRaises(ValidationError):
            self.pagar(obligaciones[0], aplicaciones=[(obligaciones[0].pk, Decimal('5'))]*2)
        pago, _ = self.pagar(obligaciones[0], aplicaciones=[(o.pk, Decimal('7.50')) for o in obligaciones])
        self.assertEqual(pago.monto_total, Decimal('15.00'))
        self.assertEqual(pago.detalles.count(), 2)

    def test_solvencia_sql_vencimiento_anuladas_y_convenios(self):
        self.matricula()
        Obligacion.objects.update(estado='ANULADA')
        o = Obligacion.objects.get(concepto__nombre='MENSUALIDAD', fecha_vencimiento='2026-06-10')
        Obligacion.objects.filter(pk=o.pk).update(estado='PENDIENTE')
        with patch('financiero.consultas.timezone.localdate', return_value=date(2026,6,10)):
            self.assertTrue(solvente(self.estudiante))
        with patch('financiero.consultas.timezone.localdate', return_value=date(2026,6,11)):
            self.assertFalse(solvente(self.estudiante))
            Obligacion.objects.update(estado='ANULADA')
            self.assertTrue(solvente(self.estudiante))
            o.refresh_from_db()
            o.estado='PENDIENTE';o.save()
            convenio = ConvenioPago.objects.create(estudiante=self.estudiante, usuario_autoriza=self.directora,
                fecha_convenio=date(2026,6,10), monto_convenido='20', numero_cuotas=1, estado='ACTIVO')
            ConvenioObligacion.objects.create(convenio=convenio, obligacion=o, saldo_incluido='20')
            self.assertTrue(solvente(self.estudiante))
            cuota = CuotaConvenio.objects.create(convenio=convenio, numero_cuota=1, fecha_vencimiento=date(2026,6,10), monto_cuota='20', estado='PENDIENTE')
            self.assertFalse(solvente(self.estudiante))
            CuotaConvenio.objects.filter(pk=cuota.pk).update(fecha_vencimiento=date(2026,6,12))
            self.assertTrue(solvente(self.estudiante))
            ConvenioPago.objects.filter(pk=convenio.pk).update(estado='INCUMPLIDO')
            self.assertFalse(solvente(self.estudiante))

    def test_convenios_no_se_cobran_por_segundo_flujo(self):
        o = self.obligacion()
        convenio = ConvenioPago.objects.create(estudiante=self.estudiante, usuario_autoriza=self.directora,
            fecha_convenio=date(2026,1,1), monto_convenido='20', numero_cuotas=1, estado='ACTIVO')
        ConvenioObligacion.objects.create(convenio=convenio, obligacion=o, saldo_incluido='20')
        with self.assertRaises(ValidationError): self.pagar(o)
        self.assertFalse(Pago.objects.exists())

    def test_permisos_por_rol_y_directora_solo_consulta(self):
        o = self.obligacion()
        pago, _ = self.pagar(o, '5')
        lectura = [reverse('finanzas_panel'), reverse('finanzas_cuenta', args=[self.estudiante.pk]), reverse('finanzas_recibo', args=[pago.pk])]
        escritura = [reverse('finanzas_pago', args=[self.estudiante.pk]), reverse('finanzas_calendario')]
        for rol in ('MAESTRO','ESTUDIANTE','PASTOR_PRINCIPAL'):
            usuario=Usuario.objects.create_user('fin-'+rol,rol+'@example.test','ficticia',rol=rol)
            self.client.force_login(usuario)
            for url in lectura+escritura:
                self.assertEqual(self.client.get(url).status_code,403)
                self.assertEqual(self.client.post(url,{}).status_code,403)
        self.client.force_login(self.directora)
        for url in lectura:self.assertEqual(self.client.get(url).status_code,200)
        for url in escritura:
            self.assertEqual(self.client.get(url).status_code,403)
            self.assertEqual(self.client.post(url,{}).status_code,403)
        with self.assertRaises(PermissionDenied): self.pagar(o,usuario=self.directora)
        for usuario in (self.secretaria,self.admin):
            self.client.force_login(usuario)
            for url in lectura+escritura:self.assertEqual(self.client.get(url).status_code,200)
        self.client.logout()
        self.assertEqual(self.client.get(lectura[0]).status_code,302)

    def test_cobro_web_recibo_reenvio_y_expediente_integrado(self):
        o = self.obligacion()
        self.client.force_login(self.secretaria)
        url = reverse('finanzas_pago',args=[self.estudiante.pk])
        form = self.client.get(url).context['form']
        datos = {'token': form.initial['token'], 'metodo':'EFECTIVO', f'importe_{o.pk}':'20.00'}
        respuesta = self.client.post(url, datos, follow=True)
        self.assertContains(respuesta,'Pago registrado correctamente')
        self.assertContains(respuesta,'Imprimir recibo')
        self.estudiante.nombres = 'Nombre posterior'
        self.estudiante.save(update_fields=['nombres'])
        recibo = self.client.get(reverse('finanzas_recibo', args=[Pago.objects.get().pk]))
        self.assertContains(recibo, 'Estudiante ficticio Prueba')
        self.assertNotContains(recibo, 'Nombre posterior')
        respuesta = self.client.post(url,datos,follow=True)
        self.assertContains(respuesta,'sin duplicarlo')
        self.assertEqual(Pago.objects.count(),1)
        self.assertContains(self.client.get(reverse('estudiante_expediente',args=[self.estudiante.pk])),reverse('finanzas_cuenta',args=[self.estudiante.pk]))
        self.assertContains(self.client.get(reverse('finanzas_cuenta',args=[self.estudiante.pk])),Pago.objects.get().numero_recibo)

    def test_interfaz_configura_calendario_y_conceptos_sin_inventar_fechas(self):
        self.client.force_login(self.secretaria)
        datos=leer(self.ciclo)
        payload={k:v for k,v in datos.items() if k not in ('periodo','meses')}
        payload['ciclo']=self.ciclo.pk
        payload.update({f'mes_{n}': mes for n,mes in enumerate(datos['meses'],1)})
        respuesta=self.client.post(reverse('finanzas_calendario'),payload,follow=True)
        self.assertContains(respuesta,'Calendario financiero guardado')
        respuesta=self.client.post(reverse('finanzas_concepto'),{'nombre':'MATRICULA','abonos':'SI'})
        self.assertContains(respuesta,'El concepto ya existe')
        self.assertFalse(ConceptoCobro.objects.get(nombre='MATRICULA').permite_abonos)
