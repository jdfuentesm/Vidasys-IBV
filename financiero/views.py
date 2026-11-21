import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_http_methods

from academico.models import Estudiante, CicloAcademico
from .calendario import guardar, leer
from .consultas import cuenta
from .forms import CalendarioForm, ConceptoForm, PagoForm
from .models import Pago, ConceptoCobro, SolicitudBeca
from .servicios import puede_cobrar, reservar_recibo, registrar_pago


def financiero(escritura=False):
    def decorar(view):
        @login_required
        @wraps(view)
        def protegida(request, *args, **kwargs):
            if not request.user.is_active or request.user.rol not in ('SECRETARIA', 'ADMINISTRADOR', 'DIRECTORA'):
                return HttpResponseForbidden('Su cuenta no tiene acceso financiero.')
            if escritura and not puede_cobrar(request.user):
                return HttpResponseForbidden('Dirección tiene acceso financiero de consulta únicamente.')
            return view(request, *args, **kwargs)
        return protegida
    return decorar


def error_formulario(form, error):
    form.add_error(None, ' '.join(error.messages) if isinstance(error, ValidationError) else
                   'La operación no se completó. Revise la configuración y el historial antes de volver a intentar.')


@financiero()
@require_http_methods(['GET'])
def panel(request):
    q = request.GET.get('q', '').strip()[:150]
    estudiantes = Estudiante.objects.order_by('apellidos', 'nombres', 'pk')
    for palabra in q.split():
        estudiantes = estudiantes.filter(Q(nombres__icontains=palabra) | Q(apellidos__icontains=palabra) | Q(codigo_estudiante__icontains=palabra))
    ciclos = []
    for ciclo in CicloAcademico.objects.order_by('-anio', 'numero_ciclo'):
        try:
            configuracion = leer(ciclo)
            detalle = f"USD 120.00 · Emisión {configuracion['emision']} · Matrícula {configuracion['matricula']} · Mensualidades: " + ', '.join(configuracion['meses'])
        except ValidationError as error:
            detalle = ' '.join(error.messages)
        ciclos.append((ciclo, detalle))
    return render(request, 'financiero/panel.html', {'pagina': Paginator(estudiantes, 20).get_page(request.GET.get('page')), 'q': q,
        'ciclos': ciclos, 'puede_cobrar': puede_cobrar(request.user)})


@financiero(escritura=True)
@require_http_methods(['GET', 'POST'])
def calendario(request):
    form = CalendarioForm(request.POST if request.method == 'POST' else None)
    conceptos = ConceptoForm()
    if request.method == 'POST' and form.is_valid():
        try:
            guardar(form.cleaned_data['ciclo'], form.configuracion())
            messages.success(request, 'Calendario financiero guardado. Ya puede matricular estudiantes en ese ciclo.')
            return redirect('finanzas_panel')
        except (ValidationError, OSError, DatabaseError) as error:
            error_formulario(form, error)
    return render(request, 'financiero/calendario.html', {'form': form, 'conceptos': conceptos})


@financiero(escritura=True)
@require_http_methods(['POST'])
def concepto(request):
    form = ConceptoForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                nombre = form.cleaned_data['nombre']
                # No sustituye catálogos ni cambia la política de un concepto previo.
                if ConceptoCobro.objects.filter(nombre__iexact=nombre).exists() or (nombre == 'MATRICULA' and ConceptoCobro.objects.filter(nombre__iexact='MATRÍCULA').exists()):
                    raise ValidationError('El concepto ya existe. Se conservó su configuración de abonos.')
                ConceptoCobro.objects.create(nombre=nombre, permite_abonos=form.cleaned_data['abonos'] == 'SI', estado='ACTIVO')
            messages.success(request, 'Concepto creado con la política de abonos seleccionada.')
            return redirect('finanzas_calendario')
        except (ValidationError, DatabaseError) as error:
            error_formulario(form, error)
    return render(request, 'financiero/calendario.html', {'form': CalendarioForm(), 'conceptos': form})


@financiero()
@require_http_methods(['GET'])
def estado_cuenta(request, estudiante_id):
    estudiante = get_object_or_404(Estudiante, pk=estudiante_id)
    try:
        datos = cuenta(estudiante)
    except DatabaseError:
        datos = {'error_cuenta': 'No se pudo consultar el estado de cuenta. Contacte a Administración; la solvencia no se puede determinar en este momento.'}
    pagos = Pago.objects.filter(estudiante=estudiante).prefetch_related('detalles__obligacion__concepto').order_by('-fecha_pago', '-pk')
    return render(request, 'financiero/cuenta.html', dict(datos, estudiante=estudiante,
        pagos=pagos, puede_cobrar=puede_cobrar(request.user),
        solicitudes_beca=SolicitudBeca.objects.filter(matricula__estudiante=estudiante).select_related('matricula__ciclo','directora')))


@financiero(escritura=True)
@require_http_methods(['GET', 'POST'])
def pago_nuevo(request, estudiante_id):
    estudiante = get_object_or_404(Estudiante, pk=estudiante_id)
    try:
        datos = cuenta(estudiante)
        token = reservar_recibo(request.user, estudiante) if request.method == 'GET' else request.POST.get('token', '')
    except (DatabaseError, ValidationError) as error:
        return render(request, 'financiero/pago.html', {'estudiante': estudiante,
            'error_pago': 'No se puede abrir el cobro. Contacte a Administración y compruebe el historial antes de volver a intentar.'}, status=503)
    # El formulario conserva importes enviados para reconocer reenvíos sin alterar el saldo mostrado.
    form = PagoForm(request.POST if request.method == 'POST' else None, filas=datos['filas'], initial={'token': token})
    if request.method == 'POST' and form.is_valid():
        try:
            pago, creado = registrar_pago(usuario=request.user, estudiante=estudiante, token=form.cleaned_data['token'],
                metodo=form.cleaned_data['metodo'], referencia=form.cleaned_data['referencia'], aplicaciones=form.aplicaciones())
            messages.success(request, 'Pago registrado correctamente.' if creado else 'Este pago ya fue registrado. Se muestra el mismo recibo sin duplicarlo.')
            return redirect('finanzas_recibo', pago_id=pago.pk)
        except (ValidationError, DatabaseError) as error:
            error_formulario(form, error)
    return render(request, 'financiero/pago.html', {'form': form, 'estudiante': estudiante})


@financiero()
@require_http_methods(['GET'])
def recibo(request, pago_id):
    pago = get_object_or_404(Pago.objects.select_related('estudiante', 'usuario').prefetch_related('detalles__obligacion__concepto', 'detalles__obligacion__matricula'), pk=pago_id)
    return presentar_recibo(request, pago)


def presentar_recibo(request, pago, *, portal=False):
    """Presentación compartida; cada endpoint debe resolver antes un pago autorizado."""
    snapshot = None
    if (pago.observaciones or '').startswith('VIDASYS_RECIBO_V1\n'):
        try:
            snapshot = json.loads(pago.observaciones.split('\n', 1)[1])
        except (ValueError, IndexError):
            pass
    return render(request, 'financiero/recibo.html', {'pago': pago, 'snapshot': snapshot, 'portal': portal})
