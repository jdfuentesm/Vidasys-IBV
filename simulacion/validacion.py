"""Aserciones independientes de F7: entradas del libro de ensayo vs fuentes reales."""
from collections import Counter
from decimal import Decimal
from time import perf_counter
from django.db import connection,reset_queries
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from academico.models import (Curso,Asistencia,Calificacion,InscripcionCurso,Estudiante,Matricula)
from financiero.models import (Caja,Pago,MovimientoCaja,Obligacion,RecepcionDonacion,Ingreso,Egreso,CuotaConvenio,ConvenioPago,Donacion)
from financiero.consultas import solvente
from reportes.financiero_consultas import generar
from reportes.financiero_forms import REPORTES
from .generador import verificar_memoria

D=Decimal
CERO=D('0.00')


def validar(e):
    verificar_memoria();t=perf_counter();esperado=e.esperados();revisiones={};tiempos={};consultas={}
    def igual(nombre,actual,ideal):
        if actual!=ideal:raise AssertionError(f'{nombre}: real={actual}, esperado={ideal}')
        revisiones[nombre]='OK'
    with e.reloj_acotado():
        datos={}
        for tipo in REPORTES:
            reset_queries()
            inicio=perf_counter()
            with CaptureQueriesContext(connection) as qs:datos[tipo]=generar(tipo,{})
            tiempos[tipo]=round(perf_counter()-inicio,4);consultas[tipo]=len(qs)
            if any(q['sql'].lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER','DROP')) for q in qs):
                raise AssertionError('Un reporte escribió datos.')
        t_res=dict(datos['resultados']['totales']);t_cue=dict(datos['cuentas']['totales']);t_ben=dict(datos['beneficios']['totales'])
        for clave,campo in [('Ingresos vigentes verificados','ingresos'),('Egresos desembolsados vigentes','egresos'),('Resultado de la selección','resultado'),('Operaciones anuladas (informativo, no sumar)','anulados')]:igual(clave,t_res[clave],esperado[campo])
        for clave,campo in [('Saldo financiero pendiente','saldo'),('Protección pendiente efectiva','cobertura'),('A cargo del estudiante, incluido convenio y no vencido','cargo_estudiantes'),('Saldo en convenio','en_convenio'),('Saldo directo del estudiante','directo'),('Control: padrinazgo + convenio + directo','saldo')]:igual(clave,t_cue[clave],esperado[campo])
        igual('Becas exoneradas',t_ben['Becas exoneradas'],esperado['becas'])
        igual('Compromisos activos pendientes',t_ben['Compromisos activos pendientes'],esperado['compromisos_pendientes'])
        igual('Recibido padrinos',t_ben['Aportes recibidos aplicados'],sum((s['recibido'] for s in esperado['padrinazgos']),CERO))
        igual('Sin pendientes de conciliación',len(datos['resultados']['avisos']),0)
        igual('40 estudiantes',Estudiante.objects.count(),40)
        igual('240 obligaciones',Obligacion.objects.count(),240)
        for ciclo in e.ciclos:igual('20 matrículas '+str(ciclo.numero_ciclo),Matricula.objects.filter(ciclo=ciclo).count(),20)
        for fila in datos['cuentas']['filas']:
            c=fila['celdas'];igual('Distribución '+c[0]+': '+c[2],c[10]+c[11]+c[12],c[9])
        filas_caja=[r['celdas'] for r in datos['cajas']['filas']]
        ret=sum((r['importe'] for r in e.dinero if not r['vigente'] and r['tipo']!='EGRESO' and r['metodo']=='EFECTIVO'),CERO)
        igual('Efectivo retenido independiente',sum((r[11] for r in filas_caja),CERO),ret)
        for salida,columna in [(False,12),(True,13)]:
            total=sum((r['importe'] for r in e.dinero if r['metodo']=='TRANSFERENCIA' and (r['tipo']=='EGRESO')==salida),CERO)
            igual('Transferencias físicas '+str(salida),sum((r[columna] for r in filas_caja),CERO),total)
        igual('Anulaciones únicas auditoría',sum(r['celdas'][2]=='ANULADO' for r in datos['auditoria']['filas']),sum(not r['vigente'] for r in e.dinero))
        # Cada origen debe tener exactamente un movimiento; no se suman sus aplicaciones.
        igual('Movimiento por pago',MovimientoCaja.objects.filter(pago__isnull=False).count(),Pago.objects.count())
        igual('Movimiento por ingreso',MovimientoCaja.objects.filter(ingreso__isnull=False).count(),Ingreso.objects.count())
        igual('Movimiento por egreso',MovimientoCaja.objects.filter(egreso__isnull=False).count(),Egreso.objects.count())
        for c in e.cierres:
            foto=Caja.objects.get(pk=c['pk']);igual(f'Foto caja {c["pk"]}',D(foto.cierre['esperado']),c['esperado'])
            igual(f'Diferencia caja {c["pk"]}',foto.diferencia,c['diferencia'])
            igual(f'Cierre caja {c["pk"]}',foto.estado,'CERRADA')
        # Solvencia independiente: vencidos fuera del convenio, cuotas vencidas y protección.
        clases=Counter();solventes=0
        por_id={x.pk:n for n,x in enumerate(e.estudiantes)}
        for n,alumno in enumerate(e.estudiantes):
            contrato=next((c for c in e.contratos if c['n']==n),None)
            vencido=CERO
            for pk,cargo in e.cargos.items():
                if cargo['estudiante']==n and cargo['vencimiento']<e.referencia and not contrato:
                    vencido+=esperado['saldos'][pk]-esperado['coberturas'][pk]
            mora_cuota=False
            if contrato:
                abonado=contrato['abonado']
                for fecha in contrato['fechas']:
                    pagado=min(abonado,D('40'));abonado-=pagado
                    if fecha<e.referencia and pagado<D('40'):mora_cuota=True
            es_solvente=vencido==0 and not mora_cuota
            igual(f'Solvencia {alumno.codigo_estudiante}',solvente(alumno),es_solvente)
            solventes+=int(es_solvente)
        igual('Solvencia sin personas duplicadas',len(datos['solvencia']['filas']),40)
        igual('Solventes independiente',sum(r['celdas'][1]!='Insolvente' for r in datos['solvencia']['filas']),solventes)
        for c in e.contratos:
            m=ConvenioPago.objects.get(pk=c['modelo'].pk)
            filas=[r['celdas'] for r in datos['convenios']['filas'] if r['celdas'][0]==str(e.estudiantes[c['n']])]
            igual(f'Convenio {m.pk} recibido',filas[0][4],c['abonado'])
            igual(f'Convenio {m.pk} diferencia',filas[0][7],CERO)
        # Estado académico real y coherencia temporal; el servicio fija resultados al cierre.
        for i in InscripcionCurso.objects.select_related('curso'):
            ausencias=Asistencia.objects.filter(inscripcion=i,estado_asistencia='AUSENTE_INJUSTIFICADA').count()
            if ausencias>=2:igual(f'Inasistencia {i.pk}',i.estado,'REPROBADA_POR_INASISTENCIA')
            elif i.curso.estado=='FINALIZADO':
                nota=e.notas[i.pk].quantize(D('.01'))
                igual(f'Resultado académico {i.pk}',i.estado,'APROBADA' if nota>=70 else 'REPROBADA_ACADEMICAMENTE')
                igual(f'Nota definitiva {i.pk}',Calificacion.objects.get(inscripcion=i).nota_final,nota)
        igual('Asistencia solo impartida',Asistencia.objects.exclude(sesion__estado='IMPARTIDA').count(),0)
        igual('Sesiones futuras no impartidas',sum(c.sesiones.filter(estado='IMPARTIDA',fecha__gt=e.referencia).count() for c in e.cursos),0)
        client=Client();client.force_login(e.directora)
        http={}
        for tipo in REPORTES:
            parametros={'desde':'','hasta':''} if 'desde' in REPORTES[tipo][1] else {}
            for formato in ('html','csv','imprimir'):
                respuesta=client.get(reverse('finanzas_reporte',args=[tipo]),{**parametros,'formato':formato})
                igual(f'HTTP {tipo} {formato}',respuesta.status_code,200)
                http[tipo+' '+formato]=respuesta.status_code
                if formato=='html' and tipo=='cuentas':igual('Paginación cuentas',len(respuesta.context_data['filas_visibles']) if hasattr(respuesta,'context_data') else respuesta.content.count(b'class="f7-registro"'),25)
        transferencia=sum((r['importe'] for r in e.dinero if r['vigente'] and r['tipo']!='EGRESO' and r['metodo']=='TRANSFERENCIA'),CERO)
        igual('Filtro método',dict(generar('resultados',{'metodo':'TRANSFERENCIA'})['totales'])['Ingresos vigentes verificados'],transferencia)
        igual('Filtro estudiante',len(generar('solvencia',{'estudiante':e.estudiantes[0]})['filas']),1)
        igual('Filtro ciclo',len(generar('cuentas',{'ciclo':e.ciclos[0]})['filas']),120)
        ingreso_mes=sum((r['importe'] for r in e.dinero if r['vigente'] and r['tipo']!='EGRESO' and r['fecha'].month==e.referencia.month),CERO)
        igual('Filtro período',dict(generar('resultados',{'desde':e.referencia.replace(day=1),'hasta':e.referencia})['totales'])['Ingresos vigentes verificados'],ingreso_mes)
        for n in (0,8,28,35,36,37):
            client.force_login(e.estudiantes[n].usuario)
            igual('Portal académico '+str(n),client.get(reverse('portal_academico')).status_code,200 if solvente(e.estudiantes[n]) else 403)
            igual('Cuenta portal '+str(n),client.get(reverse('portal_cuenta')).status_code,200)
        for rol in ('SECRETARIA','PASTOR_PRINCIPAL'):
            client.force_login(e.usuarios[rol]);igual('Permiso '+rol,client.get(reverse('finanzas_centro')).status_code,403)
    # No reutilizar el generador sobre datos existentes: no aplica ni borra dos veces.
    from .generador import generar as regenerar
    antes=Pago.objects.count()
    try:regenerar(semilla=e.semilla,referencia=e.referencia)
    except RuntimeError:igual('Reejecución bloqueada sin cambios',Pago.objects.count(),antes)
    else:raise AssertionError('Se permitió duplicar el escenario.')
    return dict(estado='CONCILIADO',comprobaciones=len(revisiones),diferencias=[],tiempos_reportes_segundos=tiempos,
        consultas_reportes=consultas,solventes=solventes,insolventes=40-solventes,http=http,
        duracion_validacion_segundos=round(perf_counter()-t,3),
        limitaciones=['No se fuerza INCUMPLIDO: no existe servicio de transición; se generan convenios ACTIVO con cuotas vencidas.',
            'El año se representa por matrícula en ciclo formativo I/III; no se inventa un campo de año del estudiante.',
            'Fechas de simulación al --fecha; saldos del navegador usan el reloj real al restaurarse el reloj acotado.',
            'SQLite no valida concurrencia ni restricciones PostgreSQL.'])
