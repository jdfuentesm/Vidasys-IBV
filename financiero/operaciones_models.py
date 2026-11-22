"""Metadatos institucionales F5; Ingreso/Egreso y categorías históricos se reutilizan."""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Inmutable(models.Model):
    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Este registro financiero es inmutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('No se elimina historial financiero.')

    class Meta:
        abstract = True


class ComprobantePrivado(Inmutable):
    nombre = models.CharField(max_length=80)
    mime = models.CharField(max_length=30)
    contenido = models.BinaryField(editable=False)
    sha256 = models.CharField(max_length=64)
    tamano = models.PositiveIntegerField()
    operador = models.ForeignKey('core.Usuario', on_delete=models.PROTECT)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'comprobante_privado'
        constraints = [models.CheckConstraint(condition=models.Q(tamano__gt=0, tamano__lte=5242880), name='comprobante_limite')]


class RegistroIngreso(Inmutable):
    clave = models.UUIDField(unique=True, editable=False)
    ingreso = models.OneToOneField('financiero.Ingreso', on_delete=models.PROTECT, related_name='registro_institucional')
    concepto = models.CharField(max_length=200)
    origen = models.CharField(max_length=200, blank=True)
    comprobante = models.ForeignKey(ComprobantePrivado, null=True, blank=True, on_delete=models.PROTECT)
    datos = models.JSONField()

    @property
    def numero(self):
        return f'ING-{self.ingreso_id:010d}'

    class Meta:
        db_table = 'registro_ingreso'


class SolicitudEgreso(models.Model):
    clave = models.UUIDField(unique=True, editable=False)
    categoria = models.ForeignKey('financiero.CategoriaEgreso', on_delete=models.PROTECT)
    concepto = models.CharField(max_length=200)
    beneficiario = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    justificacion = models.TextField()
    observaciones = models.TextField(blank=True)
    comprobante = models.ForeignKey(ComprobantePrivado, null=True, blank=True, on_delete=models.PROTECT)
    solicitante = models.ForeignKey('core.Usuario', on_delete=models.PROTECT, related_name='egresos_solicitados')
    fecha = models.DateTimeField(default=timezone.now)
    estado = models.CharField(max_length=10, default='PENDIENTE')
    directora = models.ForeignKey('core.Usuario', on_delete=models.PROTECT, null=True, blank=True, related_name='egresos_resueltos')
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    resolucion = models.TextField(blank=True)
    datos = models.JSONField()
    autorizados = models.JSONField(default=dict)

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = type(self).objects.get(pk=self.pk)
            if anterior.estado != 'PENDIENTE':
                raise ValidationError('La resolución es definitiva.')
            campos = [f.attname for f in self._meta.local_fields if f.name not in ('estado','directora','fecha_resolucion','resolucion','autorizados')]
            if any(getattr(self,c) != getattr(anterior,c) for c in campos):
                raise ValidationError('La solicitud presentada no se modifica.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('No se eliminan solicitudes.')

    class Meta:
        db_table = 'solicitud_egreso'
        ordering = ['-fecha','-pk']
        indexes = [models.Index(fields=['estado','fecha'], name='egreso_bandeja')]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gt=0), name='sol_egreso_monto'),
            models.CheckConstraint(condition=(
                models.Q(estado='PENDIENTE',directora__isnull=True,fecha_resolucion__isnull=True) |
                models.Q(estado__in=['APROBADA','RECHAZADA'],directora__isnull=False,fecha_resolucion__isnull=False)
            ), name='sol_egreso_decision'),
            models.CheckConstraint(condition=~models.Q(estado='RECHAZADA',resolucion=''),name='sol_egreso_rechazo'),
        ]


class DesembolsoEgreso(Inmutable):
    clave = models.UUIDField(unique=True, editable=False)
    solicitud = models.OneToOneField(SolicitudEgreso, on_delete=models.PROTECT, related_name='desembolso')
    egreso = models.OneToOneField('financiero.Egreso', on_delete=models.PROTECT, related_name='desembolso_institucional')
    comprobante = models.ForeignKey(ComprobantePrivado, null=True, blank=True, on_delete=models.PROTECT)
    datos = models.JSONField()

    class Meta:
        db_table = 'desembolso_egreso'


class SolicitudAnulacionOperacion(models.Model):
    clave = models.UUIDField(unique=True, editable=False)
    ingreso = models.ForeignKey(RegistroIngreso, null=True, blank=True, on_delete=models.PROTECT, related_name='anulaciones')
    desembolso = models.ForeignKey(DesembolsoEgreso, null=True, blank=True, on_delete=models.PROTECT, related_name='anulaciones')
    solicitante = models.ForeignKey('core.Usuario', on_delete=models.PROTECT, related_name='anulaciones_operacion_solicitadas')
    fecha = models.DateTimeField(default=timezone.now)
    motivo = models.TextField()
    anteriores = models.JSONField()
    estado = models.CharField(max_length=10, default='PENDIENTE')
    directora = models.ForeignKey('core.Usuario', null=True, blank=True, on_delete=models.PROTECT, related_name='anulaciones_operacion_resueltas')
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    resolucion = models.TextField(blank=True)
    aplicados = models.JSONField(default=dict)

    def save(self,*args,**kwargs):
        if self.pk:
            anterior=type(self).objects.get(pk=self.pk)
            if anterior.estado!='PENDIENTE':raise ValidationError('La resolución es definitiva.')
            for c in ('clave','ingreso_id','desembolso_id','solicitante_id','fecha','motivo','anteriores'):
                if getattr(self,c)!=getattr(anterior,c):raise ValidationError('La solicitud no se modifica.')
        return super().save(*args,**kwargs)

    def delete(self,*args,**kwargs):
        raise ValidationError('No se elimina historial.')

    class Meta:
        db_table='solicitud_anulacion_operacion'
        ordering=['-fecha','-pk']
        constraints=[
            models.CheckConstraint(condition=(models.Q(ingreso__isnull=False,desembolso__isnull=True)|models.Q(ingreso__isnull=True,desembolso__isnull=False)),name='anul_op_origen'),
            models.UniqueConstraint(fields=['ingreso'],condition=models.Q(estado='PENDIENTE'),name='anul_ing_pendiente'),
            models.UniqueConstraint(fields=['desembolso'],condition=models.Q(estado='PENDIENTE'),name='anul_egr_pendiente'),
            models.UniqueConstraint(fields=['ingreso'],condition=models.Q(estado='APROBADA'),name='anul_ing_aprobada'),
            models.UniqueConstraint(fields=['desembolso'],condition=models.Q(estado='APROBADA'),name='anul_egr_aprobada'),
            models.CheckConstraint(condition=(models.Q(estado='PENDIENTE',directora__isnull=True,fecha_resolucion__isnull=True)|models.Q(estado__in=['APROBADA','RECHAZADA'],directora__isnull=False,fecha_resolucion__isnull=False)),name='anul_op_decision'),
            models.CheckConstraint(condition=~models.Q(estado='RECHAZADA',resolucion=''),name='anul_op_rechazo'),
        ]
