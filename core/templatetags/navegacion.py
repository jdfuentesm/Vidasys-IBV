"""Presentación F8.1. Refleja accesos existentes; no concede permisos ni consulta datos."""
from django import template
from django.urls import reverse

register=template.Library()


def construir_menu(usuario,nombre=''):
    def enlace(ruta,titulo,icono,descripcion='',nombres=(),prefijo=None):
        return dict(ruta=ruta,url=reverse(ruta),titulo=titulo,icono=icono,descripcion=descripcion,
            activo=nombre in (ruta,*nombres) or bool(prefijo and nombre.startswith(prefijo)))
    inicio=enlace('dashboard','Inicio','inicio',nombres=('portal_inicio',))
    menu={'principales':[inicio],'grupos':[],'tareas':[],'otras':[],'seccion':None}
    if not usuario.is_authenticated or not usuario.is_active:return menu
    rol=usuario.rol
    estudiantes=enlace('estudiantes','Estudiantes','estudiantes','Busque un estudiante y consulte su expediente.',nombres=('estudiante_expediente','estudiante_nuevo','estudiante_editar'))
    matricula=enlace('matricula_secretaria','Matrículas','matricula','Inscriba al estudiante en el ciclo.',nombres=('estudiante_matricular',))
    cuentas=enlace('finanzas_panel','Cuentas y cobros','finanzas','Consulte saldos, registre cobros y encuentre recibos.',nombres=('finanzas_cuenta','finanzas_pago','finanzas_recibo','finanzas_calendario','finanzas_concepto'))
    generales=enlace('reportes','Reportes académicos' if rol=='MAESTRO' else 'Reportes institucionales','reportes','Consulte y exporte la información disponible para su rol.',nombres=('reportes_consultar',))
    financieros=enlace('finanzas_centro','Reportes financieros','reportes','Revise ingresos, egresos y cuentas pendientes.',nombres=('finanzas_reporte',))
    solicitudes=enlace('solicitudes_academicas','Solicitudes académicas' if rol=='DIRECTORA' else 'Mis solicitudes','autorizar','Revise solicitudes y consulte sus resoluciones.',nombres=('solicitud_academica',))
    bandeja=enlace('direccion_pendientes','Pendientes de Dirección','autorizar','Revise solicitudes y asuntos institucionales pendientes.')
    extras=enlace('autorizar_clase_extraordinaria','Clases extraordinarias','autorizar','Autorice las clases adicionales de un curso.')
    usuarios=enlace('usuarios','Usuarios y accesos','usuarios','Administre las cuentas institucionales.',prefijo='usuarios')
    cursos=enlace('mis_cursos','Mis cursos','cursos','Registre asistencia, notas y clases de sus cursos.',nombres=(
        'registrar_asistencia','registrar_calificacion','programar_sesiones','cierre_curso',
        'gestionar_sesion','solicitar_cancelacion','solicitar_correccion'))
    if rol in ('SECRETARIA','DIRECTORA','ADMINISTRADOR'):
        menu['principales'] += [estudiantes,matricula]
        finanzas=[cuentas,enlace('caja_listado','Caja y cierres','cuenta',prefijo='caja_'),
            enlace('operaciones_panel','Ingresos y egresos','finanzas',prefijo='operaciones_'),
            enlace('becas_listado','Becas','matricula',prefijo='becas_'),
            enlace('convenios_listado','Convenios de pago','cuenta',prefijo='convenios_'),
            enlace('aportes_panel','Donaciones y padrinazgos','estudiantes',prefijo='aportes_'),
            enlace('anulaciones_listado','Anulaciones de pagos','cuenta',prefijo='anulaciones_')]
        if rol=='DIRECTORA':menu['grupos'].append(dict(id='academico',titulo='Dirección académica',icono='autorizar',enlaces=[bandeja,solicitudes,extras]))
        menu['grupos'].append(dict(id='finanzas',titulo='Finanzas',icono='finanzas',enlaces=finanzas))
        menu['grupos'].append(dict(id='reportes',titulo='Reportes',icono='reportes',enlaces=[generales,financieros] if rol!='SECRETARIA' else [generales]))
        if rol=='ADMINISTRADOR':menu['principales'].append(usuarios)
    elif rol=='MAESTRO':
        menu['principales'] += [cursos,solicitudes,generales]
    elif rol=='ESTUDIANTE':
        menu['principales'] += [enlace('portal_academico','Mis materias','cursos',nombres=('portal_academico',)),
            enlace('portal_cuenta','Mi cuenta','cuenta',nombres=('portal_recibo','convenios_portal'))]
    prioridades={
        'SECRETARIA':[estudiantes,matricula,cuentas],
        'DIRECTORA':[bandeja,financieros,estudiantes],
        'ADMINISTRADOR':[cuentas,financieros,usuarios],
        'MAESTRO':[cursos],
    }
    menu['tareas']=prioridades.get(rol,[])
    otros={'SECRETARIA':[generales],'DIRECTORA':[cuentas,matricula,generales,extras],
        'ADMINISTRADOR':[estudiantes,matricula,generales],'MAESTRO':[solicitudes,generales]}
    menu['otras']=otros.get(rol,[])
    for grupo in menu['grupos']:
        grupo['activo']=any(e['activo'] for e in grupo['enlaces'])
        if grupo['activo']:menu['seccion']=grupo
    return menu


@register.simple_tag(takes_context=True)
def menu_institucional(context):
    request=context['request']
    nombre=getattr(getattr(request,'resolver_match',None),'url_name','') or ''
    return construir_menu(request.user,nombre)
