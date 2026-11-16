"""Recorrido institucional de estudiantes, con autorización antes de consultar datos."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .estudiante_forms import EstudianteForm
from .flujo_views import permitido
from .models import CicloAcademico, Estudiante, InscripcionCurso, Matricula


def gestion_estudiantes(view):
    @login_required
    @wraps(view)
    def protegida(request, *args, **kwargs):
        if not permitido(request.user, ('SECRETARIA', 'DIRECTORA', 'ADMINISTRADOR')):
            return HttpResponseForbidden('La gestión de estudiantes requiere un rol administrativo autorizado y una cuenta activa.')
        return view(request, *args, **kwargs)
    return protegida


@gestion_estudiantes
@require_http_methods(['GET'])
def estudiantes(request):
    filas = Estudiante.objects.order_by('apellidos', 'nombres', 'pk')
    q = request.GET.get('q', '').strip()[:150]
    estado = request.GET.get('estado', '').strip()[:20]
    ciclo = request.GET.get('ciclo', '')
    for palabra in q.split():
        filas = filas.filter(Q(nombres__icontains=palabra) | Q(apellidos__icontains=palabra) |
                             Q(codigo_estudiante__icontains=palabra))
    if estado:
        filas = filas.filter(estado=estado)
    if ciclo.isdecimal():
        filas = filas.filter(matriculas__ciclo_id=ciclo).distinct()
    else:
        ciclo = ''
    pagina = Paginator(filas, 20).get_page(request.GET.get('page'))
    parametros = request.GET.copy()
    parametros.pop('page', None)
    return render(request, 'academico/estudiantes/listado.html', {
        'pagina': pagina, 'q': q, 'estado': estado, 'ciclo': ciclo,
        'estados': Estudiante.objects.order_by('estado').values_list('estado', flat=True).distinct(),
        'ciclos': CicloAcademico.objects.order_by('-anio', 'numero_ciclo'),
        'parametros': parametros.urlencode(),
    })


@gestion_estudiantes
@require_http_methods(['GET', 'POST'])
def estudiante_formulario(request, estudiante_id=None):
    estudiante = get_object_or_404(Estudiante, pk=estudiante_id) if estudiante_id else None
    form = EstudianteForm(request.POST if request.method == 'POST' else None, instance=estudiante)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                registro = form.save(commit=False)
                if estudiante:
                    registro.save(update_fields=[f for f in form.Meta.fields if f not in ('codigo_estudiante', 'fecha_ingreso')])
                else:
                    registro.save()
            messages.success(request, 'Información del estudiante actualizada.' if estudiante else 'Estudiante registrado. Ya puede matricularlo desde su expediente.')
            return redirect('estudiante_expediente', estudiante_id=registro.pk)
        except IntegrityError:
            form.add_error(None, 'No se pudo guardar: hay un registro duplicado o datos incompatibles. Revise el código y vuelva a intentar.')
        except DatabaseError:
            form.add_error(None, 'No se pudo guardar la información. Intente nuevamente; si continúa, contacte a Administración.')
    return render(request, 'academico/estudiantes/formulario.html', {'form': form, 'estudiante': estudiante})


@gestion_estudiantes
@require_http_methods(['GET'])
def estudiante_expediente(request, estudiante_id):
    estudiante = get_object_or_404(Estudiante, pk=estudiante_id)
    inscripciones = InscripcionCurso.objects.select_related('curso__materia', 'curso__ciclo').order_by('curso__materia__nombre')
    matriculas = Matricula.objects.filter(estudiante=estudiante).select_related('ciclo').order_by('-fecha_matricula', '-pk').prefetch_related(
        Prefetch('inscripciones', queryset=inscripciones))
    return render(request, 'academico/estudiantes/expediente.html', {'estudiante': estudiante, 'matriculas': matriculas})
