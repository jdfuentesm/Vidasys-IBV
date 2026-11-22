"""F6: autorizaciones y aplicaciones exactas, sin DDL en tablas históricas."""
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from .operaciones_models import Inmutable


class HistorialDonante(Inmutable):
    clave=models.UUIDField(unique=True)
    donante=models.ForeignKey('financiero.Donante',on_delete=models.PROTECT)
    operador=models.ForeignKey('core.Usuario',on_delete=models.PROTECT)
    fecha=models.DateTimeField(default=timezone.now)
    datos=models.JSONField()
    anteriores=models.JSONField(default=dict)
    class Meta:db_table='historial_donante'


class SolicitudPadrinazgo(models.Model):
    clave=models.UUIDField(unique=True)
    donante=models.ForeignKey('financiero.Donante',on_delete=models.PROTECT)
    matricula=models.ForeignKey('academico.Matricula',on_delete=models.PROTECT)
    solicitante=models.ForeignKey('core.Usuario',on_delete=models.PROTECT,related_name='padrinazgos_solicitados')
    fecha=models.DateTimeField(default=timezone.now)
    propuesta=models.JSONField()
    anteriores=models.JSONField()
    estado=models.CharField(max_length=10,default='PENDIENTE')
    directora=models.ForeignKey('core.Usuario',null=True,blank=True,on_delete=models.PROTECT,related_name='padrinazgos_resueltos')
    fecha_resolucion=models.DateTimeField(null=True,blank=True)
    motivo=models.TextField(blank=True)
    padrinazgo=models.OneToOneField('financiero.Padrinazgo',null=True,blank=True,on_delete=models.PROTECT,related_name='autorizacion_institucional')
    def save(self,*a,**k):
        if self.pk:
            anterior=type(self).objects.get(pk=self.pk)
            if anterior.estado!='PENDIENTE':raise ValidationError('La autorización original es inmutable; utilice una resolución posterior.')
            for campo in ('clave','donante_id','matricula_id','solicitante_id','fecha','propuesta','anteriores'):
                if getattr(self,campo)!=getattr(anterior,campo):raise ValidationError('La solicitud presentada no se modifica.')
        return super().save(*a,**k)
    def delete(self,*a,**k):raise ValidationError('Se conserva el historial.')
    class Meta:
        db_table='solicitud_padrinazgo';ordering=['-fecha','-pk']
        constraints=[models.CheckConstraint(condition=(
            models.Q(estado='PENDIENTE',directora__isnull=True,fecha_resolucion__isnull=True,padrinazgo__isnull=True)|
            models.Q(estado='RECHAZADA',directora__isnull=False,fecha_resolucion__isnull=False,padrinazgo__isnull=True)|
            models.Q(estado='APROBADA',directora__isnull=False,fecha_resolucion__isnull=False,padrinazgo__isnull=False)),name='sol_pad_coherente')]


class CoberturaPadrinazgo(models.Model):
    solicitud=models.ForeignKey(SolicitudPadrinazgo,on_delete=models.PROTECT,related_name='coberturas')
    obligacion=models.ForeignKey('financiero.Obligacion',on_delete=models.PROTECT,related_name='coberturas_padrinazgo')
    monto=models.DecimalField(max_digits=10,decimal_places=2)
    activa=models.BooleanField(default=True)
    def save(self,*a,**k):
        if self.pk:
            viejo=type(self).objects.get(pk=self.pk)
            if (self.solicitud_id,self.obligacion_id,self.monto)!=(viejo.solicitud_id,viejo.obligacion_id,viejo.monto):raise ValidationError('La cobertura original no se modifica.')
        return super().save(*a,**k)
    def delete(self,*a,**k):raise ValidationError('Se conserva la cobertura original.')
    class Meta:
        db_table='cobertura_padrinazgo'
        constraints=[models.UniqueConstraint(fields=['solicitud','obligacion'],name='cobertura_pad_obligacion'),models.CheckConstraint(condition=models.Q(monto__gt=0),name='cobertura_pad_positiva')]


class RecepcionDonacion(Inmutable):
    clave=models.UUIDField(unique=True)
    ingreso=models.OneToOneField('financiero.Ingreso',on_delete=models.PROTECT,related_name='recepcion_donacion')
    donante=models.ForeignKey('financiero.Donante',on_delete=models.PROTECT)
    matricula=models.ForeignKey('academico.Matricula',null=True,blank=True,on_delete=models.PROTECT)
    solicitud=models.ForeignKey(SolicitudPadrinazgo,null=True,blank=True,on_delete=models.PROTECT)
    comprobante=models.ForeignKey('financiero.ComprobantePrivado',null=True,blank=True,on_delete=models.PROTECT)
    datos=models.JSONField()
    instantanea=models.JSONField(default=dict)
    @property
    def numero(self):return f'DON-{self.ingreso_id:010d}'
    class Meta:db_table='recepcion_donacion'


class LineaDonacion(Inmutable):
    recepcion=models.ForeignKey(RecepcionDonacion,on_delete=models.PROTECT,related_name='lineas')
    donacion=models.OneToOneField('financiero.Donacion',on_delete=models.PROTECT,related_name='aplicacion_institucional')
    cobertura=models.ForeignKey(CoberturaPadrinazgo,null=True,blank=True,on_delete=models.PROTECT,related_name='aportes')
    class Meta:db_table='linea_donacion'


class RevisionPadrinazgo(Inmutable):
    clave=models.UUIDField(unique=True)
    solicitud=models.ForeignKey(SolicitudPadrinazgo,on_delete=models.PROTECT,related_name='revisiones')
    directora=models.ForeignKey('core.Usuario',on_delete=models.PROTECT)
    fecha=models.DateTimeField(default=timezone.now)
    accion=models.CharField(max_length=15)
    motivo=models.TextField()
    notificacion=models.TextField(blank=True)
    anteriores=models.JSONField()
    aplicados=models.JSONField()
    class Meta:db_table='revision_padrinazgo';ordering=['-fecha','-pk']


class AnulacionDonacion(models.Model):
    clave=models.UUIDField(unique=True)
    recepcion=models.ForeignKey(RecepcionDonacion,on_delete=models.PROTECT,related_name='anulaciones')
    solicitante=models.ForeignKey('core.Usuario',on_delete=models.PROTECT,related_name='anulaciones_aporte_solicitadas')
    fecha=models.DateTimeField(default=timezone.now)
    motivo=models.TextField()
    anteriores=models.JSONField()
    estado=models.CharField(max_length=10,default='PENDIENTE')
    directora=models.ForeignKey('core.Usuario',null=True,blank=True,on_delete=models.PROTECT,related_name='anulaciones_aporte_resueltas')
    fecha_resolucion=models.DateTimeField(null=True,blank=True)
    resolucion=models.TextField(blank=True)
    aplicados=models.JSONField(default=dict)
    def save(self,*a,**k):
        if self.pk:
            viejo=type(self).objects.get(pk=self.pk)
            if viejo.estado!='PENDIENTE':raise ValidationError('La resolución es definitiva.')
            for c in ('clave','recepcion_id','solicitante_id','fecha','motivo','anteriores'):
                if getattr(self,c)!=getattr(viejo,c):raise ValidationError('La solicitud no se modifica.')
        return super().save(*a,**k)
    def delete(self,*a,**k):raise ValidationError('No se elimina historial.')
    class Meta:
        db_table='anulacion_donacion';ordering=['-fecha','-pk']
        constraints=[models.UniqueConstraint(fields=['recepcion'],condition=models.Q(estado='PENDIENTE'),name='anul_aporte_pendiente'),
            models.UniqueConstraint(fields=['recepcion'],condition=models.Q(estado='APROBADA'),name='anul_aporte_aprobada'),
            models.CheckConstraint(condition=(models.Q(estado='PENDIENTE',directora__isnull=True,fecha_resolucion__isnull=True)|models.Q(estado__in=['APROBADA','RECHAZADA'],directora__isnull=False,fecha_resolucion__isnull=False)),name='anul_aporte_resolucion')]
