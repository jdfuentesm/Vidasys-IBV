"""Proyección financiera propia para presentación. Sin donantes ni cálculo de saldos."""
from django.utils import timezone
from financiero.models import CoberturaPadrinazgo
from financiero.aportes import pendiente


def compromisos_futuros(estudiante):
    filas=[]
    qs=CoberturaPadrinazgo.objects.filter(solicitud__matricula__estudiante=estudiante,
        activa=True,solicitud__estado='APROBADA',solicitud__padrinazgo__fecha_inicio__gt=timezone.localdate()
    ).select_related('obligacion','solicitud__padrinazgo').order_by('solicitud__padrinazgo__fecha_inicio','pk')
    for cobertura in qs:
        monto=pendiente(cobertura)
        if monto>0:
            filas.append({'obligacion':cobertura.obligacion.descripcion,
                'inicio':cobertura.solicitud.padrinazgo.fecha_inicio,
                'limite':cobertura.solicitud.padrinazgo.fecha_fin,'asignacion_propia':monto})
    return filas
