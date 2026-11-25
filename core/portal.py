"""Portal de solo lectura: identidad de sesión, propiedad y solvencia en cada petición."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from academico.models import Asistencia, Estudiante, InscripcionCurso, Matricula
from financiero.consultas import cuenta, solvente
from financiero.models import Pago
from financiero.views import presentar_recibo


MENSAJE_SOLVENCIA = ('La consulta académica está temporalmente restringida. '
                    'Comuníquese con Secretaría para verificar su estado de cuenta.')


def acceso_portal(academico=False):
    def decorar(view):
        @never_cache
        @login_required
        @require_safe
        @wraps(view)
        def protegida(request, *args, **kwargs):
            if request.user.rol != 'ESTUDIANTE' or not request.user.is_active:
                return render(request, 'core/portal/aviso.html', {
                    'titulo': 'Acceso no autorizado', 'mensaje': 'El portal corresponde a cuentas estudiantiles activas.'}, status=403)
            try:
                # No se aceptan IDs, códigos, correos ni filtros del cliente para resolver identidad.
                request.estudiante = Estudiante.objects.get(usuario_id=request.user.pk)
            except (Estudiante.DoesNotExist, Estudiante.MultipleObjectsReturned):
                return render(request, 'core/portal/aviso.html', {
                    'titulo': 'Cuenta sin expediente verificado',
                    'mensaje': 'Contacte a Secretaría para verificar la vinculación de su cuenta con su expediente. No se asignará automáticamente.'}, status=403)
            if academico:
                try:
                    permitido = solvente(request.estudiante)
                except DatabaseError:
                    return render(request, 'core/portal/aviso.html', {
                        'titulo': 'Consulta académica no disponible', 'mensaje': 'No se pudo verificar su acceso. Intente más tarde o contacte a Secretaría.'}, status=503)
                if not permitido:
                    return render(request, 'core/portal/aviso.html', {
                        'titulo': 'Consulta académica restringida', 'mensaje': MENSAJE_SOLVENCIA}, status=403)
            return view(request, *args, **kwargs)
        return protegida
    return decorar


@acceso_portal()
def inicio(request):
    estudiante = request.estudiante
    habilitado = None
    try:
        habilitado = solvente(estudiante)
    except DatabaseError:
        pass
    # No consultar ni incluir matrículas o materias protegidas al estar insolvente/desconocido.
    matricula = None
    aviso_matricula = ''
    if habilitado:
        try:
            matricula = Matricula.objects.filter(estudiante=estudiante).select_related('ciclo').order_by('-fecha_matricula', '-pk').first()
        except DatabaseError:
            aviso_matricula = 'No se pudo consultar su ciclo de referencia. Intente nuevamente o contacte a Secretaría.'
    from financiero.aportes import detalle_solvencia
    cobertura=False
    aviso_cobertura=''
    if habilitado:
        try:
            cobertura=detalle_solvencia(estudiante)['por_padrinazgo']
        except DatabaseError:
            aviso_cobertura='No se pudo consultar el detalle de cobertura. Revise su estado de cuenta o contacte a Secretaría.'
    from financiero.models import RevisionPadrinazgo
    aviso_notificaciones=''
    try:
        avisos=list(RevisionPadrinazgo.objects.filter(solicitud__matricula__estudiante=estudiante).exclude(notificacion='').values('notificacion','fecha').order_by('-fecha')[:10]) if habilitado is not None else []
    except DatabaseError:
        avisos=[]
        aviso_notificaciones='No se pudieron consultar sus avisos. Intente nuevamente o contacte a Secretaría.'
    return render(request, 'core/portal/inicio.html', {
        'aviso_matricula':aviso_matricula,'aviso_notificaciones':aviso_notificaciones,'aviso_cobertura':aviso_cobertura,'notificaciones_padrinazgo':avisos,'estudiante': estudiante, 'cobertura_padrinazgo':cobertura, 'habilitado': habilitado, 'matricula': matricula, 'mensaje_solvencia': MENSAJE_SOLVENCIA})


@acceso_portal(academico=True)
def academico(request):
    try:
        inscripciones = InscripcionCurso.objects.filter(matricula__estudiante=request.estudiante).select_related('curso__materia', 'calificacion').order_by('curso__materia__nombre').prefetch_related(
            Prefetch('asistencias', queryset=Asistencia.objects.filter(inscripcion__matricula__estudiante=request.estudiante).select_related('sesion').order_by('sesion__fecha', 'sesion__numero_clase')))
        matriculas = Matricula.objects.filter(estudiante=request.estudiante).select_related('ciclo').order_by('-fecha_matricula', '-pk').prefetch_related(
            Prefetch('inscripciones', queryset=inscripciones))
        matriculas=list(matriculas)
    except DatabaseError:
        return render(request, 'core/portal/aviso.html', {'titulo':'Consulta académica no disponible',
            'mensaje':'No se pudo consultar su historial completo. Intente más tarde o contacte a Secretaría.'}, status=503)
    return render(request, 'core/portal/academico.html', {'estudiante': request.estudiante, 'matriculas': matriculas})


@acceso_portal()
def estado_cuenta(request):
    estudiante = request.estudiante
    try:
        datos = cuenta(estudiante)
    except DatabaseError:
        datos = {'error_cuenta': 'No se pudo consultar su estado de cuenta. Contacte a Secretaría; no se presume solvencia.'}
    pagos = Pago.objects.filter(estudiante=estudiante).prefetch_related('detalles__obligacion__concepto').order_by('-fecha_pago', '-pk')
    from .portal_presentacion import compromisos_futuros
    futuros=[]
    aviso_futuros=''
    if not datos.get('error_cuenta'):
        try:
            futuros=compromisos_futuros(estudiante)
        except DatabaseError:
            aviso_futuros='No se pudo consultar el detalle de compromisos futuros. No se presume cobertura adicional.'
    return render(request, 'core/portal/cuenta.html', dict(datos, estudiante=estudiante,
        pagos=pagos, puede_cobrar=False, portal=True, compromisos_futuros=futuros, aviso_futuros=aviso_futuros))


@acceso_portal()
def recibo(request, pago_id):
    # El identificador es el del comprobante; su propietario siempre se fija desde sesión.
    pago = get_object_or_404(Pago.objects.filter(estudiante=request.estudiante).select_related('estudiante', 'usuario').prefetch_related(
        'detalles__obligacion__concepto', 'detalles__obligacion__matricula'), pk=pago_id)
    return presentar_recibo(request, pago, portal=True)
