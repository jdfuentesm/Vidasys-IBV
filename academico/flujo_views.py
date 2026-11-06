from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .flujo import (autorizar_extra, cerrar_curso, firma_calendario, guardar_calendario,
                    matricular, propuesta, requisitos_cierre)
from .flujo_forms import (ExtraordinariaDireccionForm, MatriculaSecretariaForm,
                          PropuestaCalendarioForm, SesionPropuestaForm)
from .models import Curso, SesionClase


def permitido(usuario, roles):
    return usuario.is_active and usuario.rol in roles


def mostrar_error(form, error):
    if isinstance(error, ValidationError):
        form.add_error(None, ' '.join(error.messages))
    else:
        form.add_error(None, 'No se pudo guardar. Revise la configuración o recargue la página; no se guardó parcialmente.')


@login_required
def matricula_secretaria(request):
    if not permitido(request.user, ('SECRETARIA','DIRECTORA','ADMINISTRADOR')):
        return HttpResponseForbidden('La matrícula requiere Secretaría o un rol administrativo autorizado.')
    form = MatriculaSecretariaForm(request.POST or None)
    confirmacion = None
    if request.method == 'POST' and form.is_valid():
        try:
            matricula, inscripciones, creada = matricular(**form.cleaned_data)
            confirmacion = {'matricula':matricula, 'inscripciones':inscripciones}
            messages.success(request, 'Matrícula registrada con sus seis materias.' if creada else 'Matrícula existente verificada. Se conservaron sus registros y cierres.')
        except (ValidationError, DatabaseError) as error:
            mostrar_error(form,error)
    return render(request,'academico/matricula_secretaria.html',{'form':form,'confirmacion':confirmacion})


@login_required
def mis_cursos(request):
    if not permitido(request.user, ('MAESTRO',)):
        return HttpResponseForbidden('Esta pantalla corresponde a docentes activos.')
    cursos = Curso.objects.filter(maestro__usuario=request.user).select_related('materia','ciclo')
    return render(request,'academico/mis_cursos.html',{'cursos':cursos})


@login_required
def programar_sesiones(request, curso_id):
    if not permitido(request.user, ('MAESTRO',)):
        return HttpResponseForbidden('Solo el docente del curso puede proponer su calendario.')
    curso = get_object_or_404(Curso.objects.filter(maestro__usuario=request.user), pk=curso_id)
    sesiones = list(SesionClase.objects.filter(curso=curso).order_by('numero_clase'))
    revision = firma_calendario(curso,sesiones)
    configuracion = PropuestaCalendarioForm(request.POST if request.POST.get('accion') == 'proponer' else None)
    filas = []
    error_general = ''
    if request.method == 'POST' and curso.estado not in ('FINALIZADO','CANCELADO'):
        iniciales = []
        if request.POST.get('accion') == 'proponer' and configuracion.is_valid():
            d = configuracion.cleaned_data
            try:
                iniciales = propuesta(d['fecha_inicial'],d['frecuencia'],d['hora_inicio'],d['duracion_minutos'],d['intervalo_dias'])
            except (ValidationError, OverflowError) as error:
                mostrar_error(configuracion, error if isinstance(error,ValidationError) else ValidationError('Las fechas o duración exceden el intervalo admitido.'))
        elif request.POST.get('accion') == 'guardar':
            iniciales = [{'numero_clase': n} for n in range(1,7)]
        existentes = {s.numero_clase:s for s in sesiones}
        for inicial in iniciales:
            numero = inicial['numero_clase']
            if numero in existentes:
                inicial = {f:getattr(existentes[numero],f) for f in ('numero_clase','fecha','hora_inicio','hora_fin')}
            filas.append(SesionPropuestaForm(
                request.POST if request.POST.get('accion') == 'guardar' else None,
                initial=inicial, numero=numero, existente=numero in existentes, prefix=f'clase-{numero}'))
        if request.POST.get('accion') == 'guardar':
            validas = [f.is_valid() for f in filas]
            if len(filas) == 6 and all(validas):
                try:
                    cantidad = guardar_calendario(curso.pk,request.user,[f.cleaned_data for f in filas],request.POST.get('revision',''))
                    messages.success(request,f'Calendario confirmado: {cantidad} sesiones ordinarias creadas. Las existentes se conservaron.')
                    return redirect('programar_sesiones',curso_id=curso.pk)
                except (ValidationError,DatabaseError) as error:
                    error_general = ' '.join(error.messages) if isinstance(error,ValidationError) else 'No se pudo guardar el calendario; no se guardó parcialmente.'
    return render(request,'academico/programar_sesiones.html',{'curso':curso,'sesiones':sesiones,
        'configuracion':configuracion,'filas':filas,'revision':request.POST.get('revision',revision) if request.POST.get('accion')=='guardar' else revision,
        'error_general':error_general})


@login_required
def cierre_curso(request, curso_id):
    if not permitido(request.user, ('MAESTRO',)):
        return HttpResponseForbidden('Solo el docente del curso puede solicitar su cierre.')
    curso = get_object_or_404(Curso.objects.filter(maestro__usuario=request.user),pk=curso_id)
    sesiones = list(SesionClase.objects.filter(curso=curso).order_by('numero_clase'))
    revision = firma_calendario(curso,sesiones)
    if request.method == 'POST':
        try:
            cerrar_curso(curso.pk,request.user,request.POST.get('revision',''))
            messages.success(request,'Curso finalizado. No se modificaron sesiones, matrículas ni calificaciones.')
            return redirect('cierre_curso',curso_id=curso.pk)
        except (ValidationError,DatabaseError) as error:
            messages.error(request,' '.join(error.messages) if isinstance(error,ValidationError) else 'No se pudo finalizar; recargue y revise el curso.')
    errores = requisitos_cierre(curso)
    if curso.estado == 'CANCELADO': errores.append('El curso está cancelado y no puede finalizarse desde aquí.')
    return render(request,'academico/cierre_curso.html',{'curso':curso,'sesiones':sesiones,'errores':errores,'revision':revision})


@login_required
def autorizar_clase_extraordinaria(request):
    if not permitido(request.user, ('DIRECTORA',)):
        return HttpResponseForbidden('Solo una usuaria autenticada, activa y con rol DIRECTORA puede autorizar extraordinarias.')
    form = ExtraordinariaDireccionForm(request.POST or None, usuario=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            autorizar_extra(form.save(commit=False),request.user)
            messages.success(request,'Clase extraordinaria autorizada por Dirección y registrada correctamente.')
            return redirect('autorizar_clase_extraordinaria')
        except (ValidationError,DatabaseError) as error:
            mostrar_error(form,error)
    return render(request,'academico/autorizar_clase.html',{'form':form})
