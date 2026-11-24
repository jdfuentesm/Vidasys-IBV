"""Agrupación de presentación F8.2; conserva todas las filas y cifras del constructor F7."""
from collections import OrderedDict
from decimal import Decimal
from .financiero_consultas import valor


def cuentas_por_estudiante(datos):
    grupos=OrderedDict()
    columnas=datos['columnas']
    indices={nombre:columnas.index(nombre) for nombre in ('Saldo financiero','Protegido por padrinazgo','Total a cargo del estudiante')}
    for fila in datos['filas']:
        url=fila['url'];c=fila['celdas']
        if url not in grupos:
            grupos[url]={'estudiante':str(c[0]),'url':url,'saldo':Decimal('0'),'cobertura':Decimal('0'),'cargo':Decimal('0'),'obligaciones':[]}
        g=grupos[url]
        for campo,nombre in [('saldo','Saldo financiero'),('cobertura','Protegido por padrinazgo'),('cargo','Total a cargo del estudiante')]:g[campo]+=c[indices[nombre]]
        g['obligaciones'].append({'titulo':str(c[2]),'celdas':[{'etiqueta':n,'valor':valor(v)} for n,v in zip(columnas,c)]})
    for g in grupos.values():
        for clave in ('saldo','cobertura','cargo'):g[clave]=valor(g[clave])
    return list(grupos.values())


def menu_agrupado(menu):
    grupos=[('Resumen y resultado',('panel','resultados')),('Estudiantes y apoyos',('cuentas','solvencia','beneficios','convenios')),('Control y seguimiento',('cajas','auditoria'))]
    return [{'titulo':nombre,'enlaces':[m for m in menu if m['tipo'] in tipos]} for nombre,tipos in grupos]
