"""Tablas nuevas de F4; las tablas financieras históricas no se alteran."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Caja(models.Model):
    operador = models.ForeignKey('core.Usuario', on_delete=models.PROTECT)
    clave = models.UUIDField(unique=True, editable=False)
    fecha_apertura = models.DateTimeField(default=timezone.now, editable=False)
    fondo_inicial = models.DecimalField(max_digits=12, decimal_places=2)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=8, default='ABIERTA')
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    efectivo_contado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    efectivo_esperado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    diferencia = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    observaciones_cierre = models.TextField(blank=True)
    cierre = models.JSONField(default=dict)

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = type(self).objects.get(pk=self.pk)
            if anterior.estado == 'CERRADA':
                raise ValidationError('El cierre es inmutable.')
            for campo in ('operador_id', 'clave', 'fecha_apertura', 'fondo_inicial', 'observaciones'):
                if getattr(anterior, campo) != getattr(self, campo):
                    raise ValidationError('La apertura no se modifica.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('La caja se conserva como historial.')

    class Meta:
        db_table = 'caja'
        ordering = ['-fecha_apertura', '-pk']
        indexes = [models.Index(fields=['estado', 'fecha_apertura'], name='caja_estado_fecha')]
        constraints = [
            models.UniqueConstraint(fields=['operador'], condition=models.Q(estado='ABIERTA'), name='caja_abierta_operador'),
            models.CheckConstraint(condition=models.Q(fondo_inicial__gte=0), name='caja_fondo_positivo'),
            models.CheckConstraint(condition=(
                models.Q(estado='ABIERTA', fecha_cierre__isnull=True, efectivo_contado__isnull=True,
                         efectivo_esperado__isnull=True, diferencia__isnull=True) |
                models.Q(estado='CERRADA', fecha_cierre__isnull=False, efectivo_contado__gte=0,
                         efectivo_contado__isnull=False, efectivo_esperado__isnull=False, diferencia__isnull=False)
            ), name='caja_cierre_coherente'),
            models.CheckConstraint(condition=models.Q(estado='ABIERTA') | models.Q(
                diferencia=models.F('efectivo_contado') - models.F('efectivo_esperado')), name='caja_diferencia_exacta'),
        ]


class MovimientoCaja(models.Model):
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name='movimientos')
    pago = models.OneToOneField('financiero.Pago', null=True, blank=True, on_delete=models.PROTECT, related_name='movimiento_caja')
    ingreso = models.OneToOneField('financiero.Ingreso', null=True, blank=True, on_delete=models.PROTECT, related_name='movimiento_caja')
    egreso = models.OneToOneField('financiero.Egreso', null=True, blank=True, on_delete=models.PROTECT, related_name='movimiento_caja')
    fecha = models.DateTimeField(default=timezone.now, editable=False)
    operador = models.ForeignKey('core.Usuario', on_delete=models.PROTECT)
    metodo = models.CharField(max_length=15)
    importe = models.DecimalField(max_digits=10, decimal_places=2)
    referencia = models.CharField(max_length=100, blank=True)
    # El estado financiero se consulta en pago.estado. La entrada física original no se elimina.
    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Los movimientos originales son inmutables; consulte el estado del pago.')
        if self.caja.estado != 'ABIERTA' or self.caja.operador_id != self.operador_id:
            raise ValidationError('La caja no está abierta para el operador.')
        if sum(pk is not None for pk in (self.pago_id,self.ingreso_id,self.egreso_id)) != 1:
            raise ValidationError('El movimiento requiere exactamente un origen.')
        origen = self.pago if self.pago_id else self.ingreso if self.ingreso_id else self.egreso
        operador = origen.usuario_id if self.pago_id else origen.usuario_registra_id
        monto = origen.monto_total if self.pago_id else origen.monto
        if (operador != self.operador_id or origen.metodo_pago != self.metodo or
                monto != self.importe or (origen.referencia or '') != self.referencia):
            raise ValidationError('El movimiento no coincide con su recibo.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('No se eliminan movimientos.')

    class Meta:
        db_table = 'movimiento_caja'
        ordering = ['fecha', 'pk']
        constraints = [
            models.CheckConstraint(condition=(models.Q(pago__isnull=False,ingreso__isnull=True,egreso__isnull=True)|models.Q(pago__isnull=True,ingreso__isnull=False,egreso__isnull=True)|models.Q(pago__isnull=True,ingreso__isnull=True,egreso__isnull=False)), name='mov_caja_origen_unico'),
            models.CheckConstraint(condition=models.Q(importe__gt=Decimal('0')), name='mov_caja_importe_positivo'),
            models.CheckConstraint(condition=models.Q(metodo__in=['EFECTIVO', 'TRANSFERENCIA']), name='mov_caja_metodo'),
        ]


class SolicitudAnulacion(models.Model):
    clave = models.UUIDField(unique=True, editable=False)
    pago = models.ForeignKey('financiero.Pago', on_delete=models.PROTECT, related_name='solicitudes_anulacion')
    solicitante = models.ForeignKey('core.Usuario', on_delete=models.PROTECT, related_name='anulaciones_solicitadas')
    fecha_solicitud = models.DateTimeField(default=timezone.now, editable=False)
    motivo = models.TextField()
    anteriores = models.JSONField()
    estado = models.CharField(max_length=10, default='PENDIENTE')
    directora = models.ForeignKey('core.Usuario', on_delete=models.PROTECT, null=True, blank=True, related_name='anulaciones_resueltas')
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    aplicados = models.JSONField(default=dict)

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = type(self).objects.get(pk=self.pk)
            if anterior.estado != 'PENDIENTE':
                raise ValidationError('La decisión es definitiva e inmutable.')
            for campo in ('clave', 'pago_id', 'solicitante_id', 'fecha_solicitud', 'motivo', 'anteriores'):
                if getattr(anterior, campo) != getattr(self, campo):
                    raise ValidationError('La solicitud presentada no se modifica.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('No se elimina historial de anulaciones.')

    class Meta:
        db_table = 'solicitud_anulacion'
        ordering = ['-fecha_solicitud', '-pk']
        indexes = [models.Index(fields=['estado', 'fecha_solicitud'], name='anulacion_bandeja')]
        constraints = [
            models.UniqueConstraint(fields=['pago'], condition=models.Q(estado='PENDIENTE'), name='anulacion_pendiente_unica'),
            models.UniqueConstraint(fields=['pago'], condition=models.Q(estado='APROBADA'), name='anulacion_aprobada_unica'),
            models.CheckConstraint(condition=(
                models.Q(estado='PENDIENTE', directora__isnull=True, fecha_resolucion__isnull=True) |
                models.Q(estado__in=['APROBADA', 'RECHAZADA'], directora__isnull=False, fecha_resolucion__isnull=False)
            ), name='anulacion_resolucion_coherente'),
            models.CheckConstraint(condition=~models.Q(estado='RECHAZADA', observaciones=''), name='anulacion_rechazo_motivo'),
            models.CheckConstraint(condition=~models.Q(motivo=''), name='anulacion_motivo'),
        ]
