"""Datos académicos FICTICIOS y seis cuentas, exclusivamente en demo vacía."""
import json
import os
import secrets
from datetime import date, time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from core.demo_preflight import verificar_esquema_demo


class Command(BaseCommand):
    help='Sembrar una demo vacía y escribir claves aleatorias en un archivo privado fuera del repositorio.'

    def add_arguments(self,parser):
        parser.add_argument('--confirmar',action='store_true')
        parser.add_argument('--credenciales',required=True)
        parser.add_argument('--abonos-matricula',choices=('si','no'),required=True)
        parser.add_argument('--abonos-mensualidad',choices=('si','no'),required=True)

    def handle(self,*args,**options):
        if not options['confirmar']:raise CommandError('Requiere --confirmar y una base demo sin datos de aplicación.')
        verificar_esquema_demo()
        from core.models import Usuario
        from academico.models import (CicloAcademico, Curso, Estudiante, Maestro, Materia, Matricula, SesionClase, Asistencia, Calificacion)
        from academico.flujo import matricular
        from financiero.calendario import guardar
        from financiero.models import ConceptoCobro, Pago
        destino=Path(options['credenciales']).expanduser().resolve()
        publicas=[Path(settings.BASE_DIR).resolve()]
        for nombre in ('STATIC_ROOT','MEDIA_ROOT'):
            valor=getattr(settings,nombre,'')
            if valor:publicas.append(Path(valor).resolve())
        if any(destino.is_relative_to(raiz) for raiz in publicas):
            raise CommandError('Guarde las claves fuera del checkout, nunca en la imagen ni en archivos estáticos.')
        if not destino.parent.is_dir():raise CommandError('Prepare antes una carpeta privada para las credenciales.')
        descriptor=None
        creado=False
        try:
            descriptor=os.open(destino,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            creado=True
            with os.fdopen(descriptor,'w') as archivo:
                descriptor=None
                with transaction.atomic():
                    with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock(%s)',[739185294])
                    if any(m.objects.exists() for m in (Usuario,Estudiante,Maestro,CicloAcademico,Materia,Matricula,ConceptoCobro,Pago)):
                        raise CommandError('La demo contiene datos. No se sobrescribe ni se completa parcialmente.')
                    claves={}
                    usuarios={}
                    for rol,_ in Usuario.ROLES:
                        clave=secrets.token_urlsafe(24)
                        numero='demo-'+rol.lower().replace('_','-')
                        usuarios[rol]=Usuario.objects.create_user(numero,numero+'@example.test',clave,rol=rol,
                            debe_cambiar_password=True,is_staff=rol=='ADMINISTRADOR',is_superuser=rol=='ADMINISTRADOR')
                        claves[rol]={'usuario':numero,'password_temporal':clave}
                    docente=Maestro.objects.create(usuario=usuarios['MAESTRO'],nombres='DOCENTE FICTICIO',apellidos='DEMOSTRACIÓN',pais='SV',estado='ACTIVO')
                    alumno=Estudiante.objects.create(usuario=usuarios['ESTUDIANTE'],codigo_estudiante='DEMO-E001',nombres='ESTUDIANTE FICTICIO',
                        apellidos='DEMOSTRACIÓN',fecha_ingreso=date(timezone.localdate().year+1,1,1),estado='ACTIVO')
                    anio=timezone.localdate().year+1
                    ciclo=CicloAcademico.objects.create(nombre='Ciclo FICTICIO de demostración',numero_ciclo=1,anio=anio,
                        fecha_inicio=date(anio,1,1),fecha_fin=date(anio,6,30),estado='ACTIVO')
                    conceptos=[]
                    for nombre,opcion in [('MATRICULA','abonos_matricula'),('MENSUALIDAD','abonos_mensualidad')]:
                        conceptos.append(ConceptoCobro.objects.create(nombre=nombre,estado='ACTIVO',permite_abonos=options[opcion]=='si'))
                    guardar(ciclo,{'emision':f'{anio}-01-01','matricula':f'{anio}-01-10','meses':[f'{anio}-{m:02}' for m in range(2,7)],
                        'concepto_matricula':conceptos[0].pk,'concepto_mensualidad':conceptos[1].pk})
                    for n in range(1,7):
                        materia=Materia.objects.create(codigo_materia=f'DEMO-M{n:02}',nombre=f'Materia FICTICIA {n}',numero_ciclo_formativo=1,estado='ACTIVA')
                        Curso.objects.create(materia=materia,maestro=docente,ciclo=ciclo,fecha_inicio=ciclo.fecha_inicio,fecha_fin=ciclo.fecha_fin,modalidad='PRESENCIAL',estado='ACTIVO')
                    matricula,inscripciones,_=matricular(estudiante=alumno,ciclo=ciclo,numero_matricula='DEMO-MATRICULA-001',fecha_matricula=date(anio,1,2))
                    sesion=SesionClase.objects.create(curso=inscripciones[0].curso,numero_clase=1,fecha=date(anio,2,1),hora_inicio=time(8),hora_fin=time(9),estado='IMPARTIDA')
                    Asistencia.objects.create(inscripcion=inscripciones[0],sesion=sesion,estado_asistencia='PRESENTE')
                    Calificacion.objects.create(inscripcion=inscripciones[0],**dict(zip(Calificacion.COMPONENTES,[40,20,20,20,0,80,80,80,80])))
                    json.dump({'solo_demo':True,'cambio_obligatorio':True,'cuentas':claves},archivo,ensure_ascii=False,indent=2)
                    archivo.flush();os.fsync(archivo.fileno())
            self.stdout.write(self.style.SUCCESS('Demo ficticia preparada. Credenciales guardadas en el archivo privado indicado; no se muestran en logs. No vuelva a sembrar esta base.'))
        except Exception:
            if descriptor is not None:os.close(descriptor)
            if creado:destino.unlink(missing_ok=True)
            raise
