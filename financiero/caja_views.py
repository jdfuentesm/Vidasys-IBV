"""Interfaz institucional F4; los servicios repiten los controles de permisos."""
import csv
from decimal import Decimal
from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from core.models import Usuario
from reportes.views import celda_csv
from . import caja, anulaciones
from .becas_views import error
from .caja_forms import AperturaForm, CierreForm, AnulacionForm, DecisionForm, FechasForm
from .models import Caja, Pago, SolicitudAnulacion


def acceso(roles):
    def decorar(view):
        @login_required
        @wraps(view)
        def protegida(request, *args, **kwargs):
            if not request.user.is_active or request.user.rol not in roles:
                return HttpResponseForbidden('Su cuenta no puede realizar esta operación financiera.')
            return view(request, *args, **kwargs)
        return protegida
    return decorar


def _csv(nombre, cabecera, filas):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nombre}.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(cabecera)
    for fila in filas:
        writer.writerow([celda_csv(v) for v in fila])
    return response


def _fechas(qs, form, campo):
    if not form.is_valid():
        return qs.none()
    for parametro, lookup in [('desde', 'gte'), ('hasta', 'lte')]:
        if form.cleaned_data.get(parametro):
            qs = qs.filter(**{f'{campo}__date__{lookup}': form.cleaned_data[parametro]})
    return qs


@acceso(caja.LECTORES)
@require_http_methods(['GET'])
def listado(request):
    qs = Caja.objects.select_related('operador')
    propia = request.user.rol == 'SECRETARIA'
    if propia:
        qs = qs.filter(operador=request.user)
    elif request.GET.get('operador', '').isdigit():
        qs = qs.filter(operador_id=int(request.GET['operador']))
    if request.GET.get('estado') in ('ABIERTA', 'CERRADA'):
        qs = qs.filter(estado=request.GET['estado'])
    fechas = FechasForm(request.GET)
    qs = _fechas(qs, fechas, 'fecha_apertura')
    if request.GET.get('formato') == 'csv':
        filas = []
        for c in qs:
            foto = c.cierre if c.estado == 'CERRADA' else caja.totales(c)
            filas.append([c.pk, c.operador.numero_usuario, c.fecha_apertura.isoformat(), c.estado,
                foto['efectivo_vigente'], foto['transferencias_vigentes'], foto['anulados'], foto['esperado'],
                c.efectivo_contado if c.efectivo_contado is not None else '', c.diferencia if c.diferencia is not None else ''])
        return _csv('cajas', ['Caja', 'Operador', 'Apertura', 'Estado', 'Efectivo vigente', 'Transferencias vigentes', 'Anulados', 'Efectivo esperado', 'Contado', 'Diferencia'], filas)
    return render(request, 'financiero/caja/listado.html', {'pagina': Paginator(qs, 20).get_page(request.GET.get('page')),
        'fechas': fechas, 'operadores': Usuario.objects.filter(rol__in=caja.OPERADORES).order_by('numero_usuario') if not propia else [],
        'puede_operar': request.user.rol in caja.OPERADORES, 'filtros': request.GET.urlencode(),
        'actual': Caja.objects.filter(operador=request.user, estado='ABIERTA').first()})


@acceso(caja.OPERADORES)
@require_http_methods(['GET', 'POST'])
def apertura(request):
    form = AperturaForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            c = caja.abrir(usuario=request.user, **form.cleaned_data)
            messages.success(request, 'Caja abierta. Los nuevos cobros quedarán vinculados a esta caja.')
            return redirect('caja_detalle', caja_id=c.pk)
        except (ValidationError, DatabaseError) as ex:
            error(form, ex)
    return render(request, 'financiero/caja/form.html', {'form': form, 'titulo': 'Abrir caja propia', 'accion': 'Abrir caja'})


@acceso(caja.LECTORES)
@require_http_methods(['GET'])
def detalle(request, caja_id):
    qs = Caja.objects.select_related('operador')
    if request.user.rol == 'SECRETARIA':
        qs = qs.filter(operador=request.user)
    c = get_object_or_404(qs, pk=caja_id)
    foto = c.cierre if c.estado == 'CERRADA' else caja.totales(c)
    if request.GET.get('formato') == 'csv':
        return _csv(f'caja-{c.pk}-movimientos', ['Recibo', 'Fecha', 'Operador', 'Método', 'Importe', 'Estado', 'Referencia'],
            [[m['numero'], m['fecha'], m['operador'], m['metodo'], m['importe'], m['estado'], m['referencia']] for m in foto['movimientos']])
    return render(request, 'financiero/caja/detalle.html', {'caja': c, 'totales': foto,
        'puede_cerrar': c.estado == 'ABIERTA' and c.operador_id == request.user.pk and request.user.rol in caja.OPERADORES})


@acceso(caja.OPERADORES)
@require_http_methods(['GET', 'POST'])
def cierre(request, caja_id):
    c = get_object_or_404(Caja, pk=caja_id, operador=request.user)
    if request.method == 'GET' and c.estado == 'CERRADA':
        return redirect('caja_detalle', caja_id=c.pk)
    form = CierreForm(request.POST if request.method == 'POST' else None)
    comparacion = None
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            if request.POST.get('accion') == 'confirmar':
                caja.cerrar(usuario=request.user, caja_id=c.pk, **d)
                messages.success(request, 'Caja cerrada. El arqueo y sus movimientos históricos quedan conservados.')
                return redirect('caja_detalle', caja_id=c.pk)
            comparacion, token = caja.preparar_cierre(usuario=request.user, caja_id=c.pk,
                contado=d['contado'], observaciones=d['observaciones'])
            form.data = form.data.copy()
            form.data['revision'] = token
        except (ValidationError, DatabaseError) as ex:
            error(form, ex)
    return render(request, 'financiero/caja/form.html', {'form': form, 'titulo': f'Cierre y arqueo de caja #{c.pk}',
        'accion': 'Comparar arqueo', 'comparacion': comparacion, 'caja': c,
        'diferencia': form.cleaned_data['contado'] - Decimal(comparacion['esperado']) if comparacion else None, 'totales': caja.totales(c) if c.estado == 'ABIERTA' else c.cierre})


@acceso(caja.LECTORES)
@require_http_methods(['GET'])
def anulaciones_listado(request):
    pagos = Pago.objects.select_related('estudiante', 'usuario').order_by('-fecha_pago', '-pk')
    q = request.GET.get('q', '').strip()[:150]
    if q:
        pagos = pagos.filter(Q(numero_recibo__icontains=q) | Q(referencia__icontains=q) |
            Q(estudiante__codigo_estudiante__icontains=q) | Q(estudiante__nombres__icontains=q) | Q(estudiante__apellidos__icontains=q))
    fechas = FechasForm(request.GET)
    pagos = _fechas(pagos, fechas, 'fecha_pago')
    solicitudes = SolicitudAnulacion.objects.select_related('pago', 'solicitante', 'directora')
    if request.GET.get('estado') in ('PENDIENTE', 'APROBADA', 'RECHAZADA'):
        solicitudes = solicitudes.filter(estado=request.GET['estado'])
    return render(request, 'financiero/anulaciones/listado.html', {'pagos': Paginator(pagos, 20).get_page(request.GET.get('page')),
        'solicitudes': Paginator(solicitudes, 20).get_page(request.GET.get('sol_page')), 'q': q, 'fechas': fechas,
        'filtros': request.GET.urlencode()})


@acceso(('SECRETARIA',))
@require_http_methods(['GET', 'POST'])
def anulacion_nueva(request, pago_id):
    pago = get_object_or_404(Pago.objects.select_related('estudiante', 'usuario'), pk=pago_id)
    pendiente = pago.solicitudes_anulacion.filter(estado='PENDIENTE').first()
    if pendiente:
        return redirect('anulaciones_detalle', solicitud_id=pendiente.pk)
    form = AnulacionForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            s = anulaciones.solicitar(usuario=request.user, pago_id=pago.pk, **form.cleaned_data)
            messages.success(request, 'Solicitud registrada. Los saldos no cambian hasta que Dirección apruebe.')
            return redirect('anulaciones_detalle', solicitud_id=s.pk)
        except (ValidationError, DatabaseError) as ex:
            error(form, ex)
    return render(request, 'financiero/anulaciones/nueva.html', {'form': form, 'pago': pago})


@acceso(caja.LECTORES)
@require_http_methods(['GET', 'POST'])
def anulacion_detalle(request, solicitud_id):
    s = get_object_or_404(SolicitudAnulacion.objects.select_related('pago__estudiante', 'pago__usuario', 'solicitante', 'directora'), pk=solicitud_id)
    if request.method == 'POST' and request.user.rol != 'DIRECTORA':
        return HttpResponseForbidden('Solo Dirección puede resolver anulaciones.')
    form = DecisionForm(request.POST if request.method == 'POST' else None)
    comparacion = False
    if request.method == 'POST' and form.is_valid():
        try:
            d = form.cleaned_data
            if d['decision'] == 'APROBADA' and request.POST.get('accion') != 'resolver':
                token = anulaciones.previsualizar(usuario=request.user, solicitud_id=s.pk, observaciones=d['observaciones'])
                form.data = form.data.copy()
                form.data['revision'] = token
                comparacion = True
            else:
                anulaciones.resolver(usuario=request.user, solicitud_id=s.pk, **d)
                messages.success(request, 'Resolución registrada. No se realizó ninguna devolución de fondos.')
                return redirect('anulaciones_detalle', solicitud_id=s.pk)
        except PermissionDenied:
            return HttpResponseForbidden('Solo Dirección activa puede aprobar o rechazar.')
        except (ValidationError, DatabaseError) as ex:
            error(form, ex)
    return render(request, 'financiero/anulaciones/detalle.html', {'solicitud': s, 'form': form, 'comparacion': comparacion,
        'consecuencias': anulaciones.consecuencias(s.pago) if s.estado == 'PENDIENTE' else [],
        'convenio': s.pago.aplicaciones_cuotas.select_related('cuota__convenio').first()})
