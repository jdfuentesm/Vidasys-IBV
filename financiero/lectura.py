"""Lectura por lotes compartida por portal y F7. No guarda ni recalcula estados."""
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal
from django.db import connection,transaction
from django.db.models import Sum
from django.utils import timezone
from academico.models import Estudiante
from .models import (Obligacion,DetallePago,Donacion,CoberturaPadrinazgo,LineaDonacion,
    AplicacionBeca,ConvenioPago,ConvenioObligacion,CuotaConvenio,AplicacionPagoCuota)

CERO=Decimal('0.00')


@contextmanager
def lectura_consistente():
    anidada=connection.in_atomic_block
    with transaction.atomic():
        if connection.vendor=='postgresql' and not anidada:
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        yield


class EstadoFinanciero:
    """Número acotado de lecturas; cada obligación, cuota y estudiante aparece una vez."""
    def __init__(self,estudiantes=None):
        self.hoy=timezone.localdate()
        self.estudiantes=list(Estudiante.objects.order_by('apellidos','nombres','pk') if estudiantes is None else estudiantes)
        ids=[e.pk for e in self.estudiantes]
        self.obligaciones=list(Obligacion.objects.filter(matricula__estudiante_id__in=ids).select_related('matricula__estudiante','matricula__ciclo','concepto').order_by('pk'))
        oids=[o.pk for o in self.obligaciones]
        pagos=dict(DetallePago.objects.filter(obligacion_id__in=oids,pago__estado='REGISTRADO').values('obligacion_id').annotate(n=Sum('monto_aplicado')).values_list('obligacion_id','n'))
        donaciones=dict(Donacion.objects.filter(obligacion_id__in=oids,estado='RECIBIDA').values('obligacion_id').annotate(n=Sum('monto')).values_list('obligacion_id','n'))
        beneficios=dict(AplicacionBeca.objects.filter(obligacion_id__in=oids,estado='APLICADA').values('obligacion_id').annotate(n=Sum('monto_aplicado')).values_list('obligacion_id','n'))
        coberturas=list(CoberturaPadrinazgo.objects.filter(obligacion_id__in=oids,activa=True,solicitud__estado='APROBADA').select_related('solicitud__padrinazgo'))
        recibidos=dict(LineaDonacion.objects.filter(cobertura_id__in=[c.pk for c in coberturas],donacion__estado='RECIBIDA').values('cobertura_id').annotate(n=Sum('donacion__monto')).values_list('cobertura_id','n'))
        self.pendientes_cobertura={c.pk:max(c.monto-recibidos.get(c.pk,CERO),CERO) for c in coberturas}
        protegidos=defaultdict(lambda:CERO);reservas=defaultdict(lambda:CERO)
        for c in coberturas:
            restante=self.pendientes_cobertura[c.pk];reservas[c.obligacion_id]+=restante
            if c.solicitud.padrinazgo.fecha_inicio<=self.hoy:protegidos[c.obligacion_id]+=restante
        self.convenios=list(ConvenioPago.objects.filter(estudiante_id__in=ids).select_related('estudiante').order_by('pk'))
        cids=[c.pk for c in self.convenios]
        self.enlaces=list(ConvenioObligacion.objects.filter(convenio_id__in=cids).order_by('pk'))
        self.cuotas=list(CuotaConvenio.objects.filter(convenio_id__in=cids).order_by('pk'))
        abonado=dict(AplicacionPagoCuota.objects.filter(cuota_id__in=[q.pk for q in self.cuotas],pago__estado='REGISTRADO').values('cuota_id').annotate(n=Sum('monto_aplicado')).values_list('cuota_id','n'))
        self.convenios_por_id={c.pk:c for c in self.convenios}
        self.convenios_obligacion=defaultdict(list)
        for e in self.enlaces:self.convenios_obligacion[e.obligacion_id].append(self.convenios_por_id[e.convenio_id])
        self.cuotas_por_convenio=defaultdict(list)
        for q in self.cuotas:
            pago=abonado.get(q.pk,CERO);saldo=max(q.monto_cuota-pago,CERO) if q.estado!='ANULADA' else CERO
            self.cuotas_por_convenio[q.convenio_id].append({'cuota':q,'abonado':pago,'saldo':saldo,'vencida':q.estado!='ANULADA' and saldo>0 and q.fecha_vencimiento<self.hoy})
        self.filas=[];self.por_obligacion={};self.por_estudiante=defaultdict(list)
        for o in self.obligaciones:
            pagado=pagos.get(o.pk,CERO);donado=donaciones.get(o.pk,CERO)
            saldo=max(o.monto_final-pagado-donado,CERO)
            proteccion=min(saldo,protegidos[o.pk]) if o.estado!='ANULADA' else CERO
            convenios=self.convenios_obligacion[o.pk]
            en_convenio=any(c.estado in ('ACTIVO','CUMPLIDO','INCUMPLIDO') for c in convenios)
            cuota=max(saldo-proteccion,CERO) if en_convenio and o.estado!='ANULADA' else CERO
            directo=max(saldo-proteccion-cuota,CERO) if o.estado!='ANULADA' else CERO
            f={'obligacion':o,'pagado':pagado,'donado':donado,'beca':beneficios.get(o.pk,CERO),'saldo':saldo,
               'cobertura':proteccion,'reserva':reservas[o.pk],'convenio':cuota,'directo':directo,
               'cargo_estudiante':max(saldo-proteccion,CERO),'vencida':o.fecha_vencimiento<self.hoy,
               'anulada':o.estado=='ANULADA','sobreaplicado':max(pagado+donado-o.monto_final,CERO)}
            self.filas.append(f);self.por_obligacion[o.pk]=f;self.por_estudiante[o.matricula.estudiante_id].append(f)
        self.solvencias=self._solvencias()

    def _solvencias(self):
        ids=[e.pk for e in self.estudiantes];base={}
        # Misma función original, invocada por lote; sin una consulta de red por estudiante.
        for inicio in range(0,len(ids),400):
            lote=ids[inicio:inicio+400]
            with connection.cursor() as cursor:
                cursor.execute('SELECT id_estudiante, estudiante_esta_solvente(id_estudiante, %s) FROM estudiante WHERE id_estudiante IN ('+','.join(['%s']*len(lote))+')',[self.hoy,*lote])
                base.update((pk,bool(valor)) for pk,valor in cursor.fetchall())
        conflictos=set()
        for c in self.convenios:
            if c.estado=='INCUMPLIDO' or (c.estado=='ACTIVO' and any(f['vencida'] for f in self.cuotas_por_convenio[c.pk])):conflictos.add(c.estudiante_id)
        resultado={}
        for e in self.estudiantes:
            filas=[f for f in self.por_estudiante[e.pk] if not f['anulada']]
            saldo=sum((f['saldo'] for f in filas),CERO);protegido=sum((f['cobertura'] for f in filas),CERO)
            exigible=sum((f['cargo_estudiante'] for f in filas if f['vencida'] and not any(c.estado in ('ACTIVO','CUMPLIDO') for c in self.convenios_obligacion[f['obligacion'].pk])),CERO)
            if e.pk not in base:
                # Preserva el error de la función original para identidades inexistentes.
                with connection.cursor() as cursor:cursor.execute('SELECT estudiante_esta_solvente(%s,%s)',[e.pk,self.hoy]);base[e.pk]=bool(cursor.fetchone()[0])
            solvente=base[e.pk] or (protegido>0 and exigible==0 and e.pk not in conflictos)
            convenio=any(f['saldo']>0 and any(c.estado in ('ACTIVO','CUMPLIDO') for c in self.convenios_obligacion[f['obligacion'].pk]) for f in filas)
            beca=any(f['beca']>0 for f in filas)
            clase='INSOLVENTE' if not solvente else 'COMBINADA' if sum((protegido>0,convenio,beca))>=2 else 'PADRINAZGO' if protegido>0 else 'CONVENIO' if convenio else 'SOLVENTE'
            resultado[e.pk]={'solvente':solvente,'por_padrinazgo':bool(solvente and protegido>0),'clase':clase,
                'saldo_financiero':saldo,'cobertura_autorizada':protegido,'saldo_estudiante':saldo-protegido,
                'filas':[{'obligacion':f['obligacion'].pk,'saldo':str(f['saldo']),'cobertura':str(f['cobertura']),'cargo':str(f['cargo_estudiante'])} for f in filas]}
        return resultado
