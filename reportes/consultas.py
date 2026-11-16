"""Lecturas institucionales. No recalcula notas ni modifica estados o registros."""
from decimal import Decimal
from django.db.models import Prefetch
from django.core.exceptions import PermissionDenied
from .catalogo import CATALOGO

from academico.models import Asistencia, InscripcionCurso, Matricula
from financiero.consultas import importes, solvente
from financiero.models import ConvenioObligacion, DetallePago, Ingreso, Obligacion, Pago

CERO=Decimal('0.00')


def dinero(importe):return f'USD {importe:.2f}'


def periodo(qs,campo,filtros):
    if filtros.get('desde'):qs=qs.filter(**{campo+'__gte':filtros['desde']})
    if filtros.get('hasta'):qs=qs.filter(**{campo+'__lte':filtros['hasta']})
    return qs


def filtrar(qs,filtros,*,ciclo,curso,estudiante):
    for clave,ruta in [('ciclo',ciclo),('curso',curso),('estudiante',estudiante)]:
        if filtros.get(clave):qs=qs.filter(**{ruta:filtros[clave].pk})
    return qs


def inscripciones(usuario,filtros):
    qs=InscripcionCurso.objects.select_related('matricula__estudiante','matricula__ciclo','curso__materia','calificacion')
    if usuario.rol=='MAESTRO':qs=qs.filter(curso__maestro__usuario=usuario)
    return filtrar(qs,filtros,ciclo='matricula__ciclo_id',curso='curso_id',estudiante='matricula__estudiante_id')


def obligaciones(filtros):
    qs=Obligacion.objects.exclude(estado='ANULADA').select_related('matricula__estudiante','matricula__ciclo','concepto')
    if filtros.get('ciclo'):qs=qs.filter(matricula__ciclo=filtros['ciclo'])
    if filtros.get('estudiante'):qs=qs.filter(matricula__estudiante=filtros['estudiante'])
    if filtros.get('curso'):
        # Un cargo pertenece a la matrícula, no a una materia: incluirlo una sola vez.
        qs=qs.filter(matricula_id__in=InscripcionCurso.objects.filter(curso=filtros['curso']).values('matricula_id'))
    return periodo(qs,'fecha_vencimiento',filtros).order_by('fecha_vencimiento','pk')


def pagos(filtros):
    qs=Pago.objects.filter(estado='REGISTRADO').select_related('estudiante')
    if filtros.get('estudiante'):qs=qs.filter(estudiante=filtros['estudiante'])
    detalles=DetallePago.objects.select_related('obligacion__matricula')
    if filtros.get('ciclo'):detalles=detalles.filter(obligacion__matricula__ciclo=filtros['ciclo'])
    if filtros.get('curso'):
        detalles=detalles.filter(obligacion__matricula_id__in=InscripcionCurso.objects.filter(curso=filtros['curso']).values('matricula_id'))
    acotado=bool(filtros.get('ciclo') or filtros.get('curso'))
    if acotado:qs=qs.filter(pk__in=detalles.values('pago_id'))
    qs=periodo(qs,'fecha_pago__date',filtros).prefetch_related(Prefetch('detalles',queryset=detalles,to_attr='aplicaciones_filtradas')).order_by('fecha_pago','pk')
    return [(p,sum((d.monto_aplicado for d in p.aplicaciones_filtradas),CERO) if acotado else p.monto_total) for p in qs]


def generar(tipo,usuario,filtros):
    if tipo not in CATALOGO or not usuario.is_active or usuario.rol not in CATALOGO[tipo][1]:
        raise PermissionDenied('Reporte no autorizado para este rol.')
    filas=[];totales=[];nota=''
    if tipo=='matriculas':
        qs=Matricula.objects.select_related('estudiante','ciclo')
        if filtros.get('ciclo'):qs=qs.filter(ciclo=filtros['ciclo'])
        if filtros.get('estudiante'):qs=qs.filter(estudiante=filtros['estudiante'])
        if filtros.get('curso'):qs=qs.filter(pk__in=InscripcionCurso.objects.filter(curso=filtros['curso']).values('matricula_id'))
        registros=list(periodo(qs,'fecha_matricula',filtros).order_by('ciclo__anio','ciclo__numero_ciclo','estudiante__apellidos','pk'))
        columnas=['Ciclo','Matrícula','Código','Estudiante','Fecha de matrícula','Estado']
        filas=[[str(m.ciclo),m.numero_matricula,m.estudiante.codigo_estudiante,f'{m.estudiante.nombres} {m.estudiante.apellidos}',str(m.fecha_matricula),m.estado] for m in registros]
        totales=[('Matrículas',len(registros)),('Estudiantes distintos',len({m.estudiante_id for m in registros}))]
    elif tipo in ('inscripciones','calificaciones','estados'):
        campo='fecha_inscripcion' if tipo=='inscripciones' else 'matricula__fecha_matricula'
        registros=list(periodo(inscripciones(usuario,filtros),campo,filtros).order_by('matricula__ciclo__anio','curso__materia__nombre','matricula__estudiante__apellidos','pk'))
        columnas=['Ciclo','Curso','Materia','Código','Estudiante','Estado de inscripción']
        if tipo=='calificaciones':columnas+=['Nota final registrada','Estado de calificación']
        for i in registros:
            e=i.matricula.estudiante
            fila=[str(i.matricula.ciclo),str(i.curso_id),i.curso.materia.nombre,e.codigo_estudiante,f'{e.nombres} {e.apellidos}',i.estado]
            if tipo=='calificaciones':
                nota_registrada=getattr(i,'calificacion',None)
                fila+=[str(nota_registrada.nota_final) if nota_registrada and nota_registrada.nota_final is not None else 'Sin nota final',
                       nota_registrada.get_estado_display() if nota_registrada else 'Sin calificación registrada']
            filas.append(fila)
        totales=[('Inscripciones',len(registros)),('Estudiantes distintos',len({i.matricula.estudiante_id for i in registros})),('Cursos distintos',len({i.curso_id for i in registros}))]
        nota='Los estados se muestran como están registrados. No se infiere «incompleto» ni reprobación a partir de una nota ausente.'
    elif tipo=='asistencia':
        qs=Asistencia.objects.filter(inscripcion__in=inscripciones(usuario,filtros)).select_related('inscripcion__curso__materia','inscripcion__matricula__estudiante','inscripcion__matricula__ciclo','sesion')
        registros=list(periodo(qs,'sesion__fecha',filtros).order_by('inscripcion__curso_id','inscripcion__matricula__estudiante__apellidos','sesion__fecha','pk'))
        columnas=['Ciclo','Curso','Materia','Código','Estudiante','Fecha','Clase','Asistencia registrada']
        for a in registros:
            i=a.inscripcion;e=i.matricula.estudiante
            filas.append([str(i.matricula.ciclo),str(i.curso_id),i.curso.materia.nombre,e.codigo_estudiante,f'{e.nombres} {e.apellidos}',str(a.sesion.fecha),str(a.sesion.numero_clase),a.get_estado_asistencia_display()])
        totales=[('Registros de asistencia',len(registros))]
        nota='Solo se incluyen asistencias registradas. La ausencia de un registro no se interpreta como una falta.'
    elif tipo=='pagos':
        registros=pagos(filtros)
        columnas=['Recibo','Fecha local','Código','Estudiante','Método','Importe del reporte','Total del recibo (informativo)']
        from django.utils import timezone
        filas=[[p.numero_recibo,timezone.localtime(p.fecha_pago).strftime('%Y-%m-%d %H:%M'),p.estudiante.codigo_estudiante,f'{p.estudiante.nombres} {p.estudiante.apellidos}',p.metodo_pago,dinero(monto),dinero(p.monto_total)] for p,monto in registros]
        totales=[('Pagos registrados',len(registros)),('Importe del reporte',dinero(sum((monto for _,monto in registros),CERO)))]
        nota='Solo pagos REGISTRADO. Con filtro de ciclo/curso, el importe corresponde a detalles de las matrículas seleccionadas, sin sumar repetidamente el total del recibo. El cargo no se atribuye económicamente a una materia.'
    elif tipo in ('pendientes','resumen'):
        registros=[];saldos=CERO
        for o in obligaciones(filtros):
            pagado,donado,saldo=importes(o)
            if saldo>0:registros.append((o,pagado,donado,saldo));saldos+=saldo
        if tipo=='pendientes':
            columnas=['Ciclo','Matrícula','Código','Estudiante','Obligación','Vencimiento','Monto final','Pagos registrados','Donaciones recibidas','Saldo actual','Convenio','Solvencia actual']
            solvencias={}
            for o,pagado,donado,saldo in registros:
                e=o.matricula.estudiante
                if e.pk not in solvencias:solvencias[e.pk]='SOLVENTE' if solvente(e) else 'INSOLVENTE'
                convenio=ConvenioObligacion.objects.filter(obligacion=o,convenio__estado__in=('ACTIVO','CUMPLIDO')).exists()
                filas.append([str(o.matricula.ciclo),o.matricula.numero_matricula,e.codigo_estudiante,f'{e.nombres} {e.apellidos}',o.descripcion,str(o.fecha_vencimiento),dinero(o.monto_final),dinero(pagado),dinero(donado),dinero(saldo),'Cobertura existente' if convenio else 'Sin cobertura activa/cumplida',solvencias[e.pk]])
            totales=[('Obligaciones con saldo',len(registros)),('Saldo actual',dinero(saldos))]
        else:
            ingresos_pago=pagos(filtros)
            columnas=['Indicador','Importe USD','Alcance']
            filas=[['Pagos de estudiantes registrados',dinero(sum((importe for _,importe in ingresos_pago),CERO)),'Fecha del pago; aplicaciones filtradas si se indica ciclo/curso'],
                   ['Saldo actual por cobrar',dinero(saldos),'Obligaciones no anuladas; fechas filtran su vencimiento']]
            if not any(filtros.get(k) for k in ('ciclo','curso','estudiante')):
                ingresos=periodo(Ingreso.objects.filter(estado='REGISTRADO'),'fecha_ingreso__date',filtros)
                # Tabla independiente: nunca se suma con Pago al no existir un vínculo de conciliación.
                from django.db.models import Sum
                total=ingresos.aggregate(total=Sum('monto'))['total'] or CERO
                filas.append(['Ingresos administrativos registrados (registro independiente)',dinero(total),'Registro independiente; no sumar con pagos sin conciliación'])
            else:
                filas.append(['Ingresos administrativos por ciclo/curso/estudiante','No disponible','Los ingresos administrativos no se vinculan a estos filtros; no se atribuyen importes por coincidencias'])
            totales=[('Pagos de estudiantes',len(ingresos_pago)),('Obligaciones con saldo',len(registros))]
        nota='El filtro de curso selecciona matrículas con inscripción, no distribuye la tarifa por materia. Saldos actuales, no reconstrucción histórica al corte. Los convenios no borran deuda; la solvencia usa la función institucional existente. No se suman pagos con ingresos administrativos, porque no hay un vínculo que permita descartar doble registro.'
    else:
        raise ValueError('Reporte desconocido')
    return {'columnas':columnas,'filas':filas,'totales':totales,'nota':nota}
