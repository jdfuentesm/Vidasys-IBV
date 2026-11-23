"""F7.1: escenario reproducible. Solo catálogo/perfiles se crean directamente.
Operaciones financieras y autorizaciones pasan por servicios institucionales.
El reloj afecta únicamente este proceso durante generar(); nunca las reglas.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import date,datetime,time,timedelta
from decimal import Decimal
import random
import secrets
from time import perf_counter
from unittest.mock import patch
from uuid import uuid5,NAMESPACE_URL
from django.conf import settings
from django.db import connection,transaction
from django.utils import timezone
from core.models import Usuario
from academico.models import (Estudiante,Maestro,Materia,CicloAcademico,Curso,Matricula,
    InscripcionCurso,SesionClase,Asistencia,Calificacion,SolicitudAcademica)
from academico import flujo,solicitudes,correcciones
from financiero import calendario,becas,aportes,convenios,operaciones,caja,anulaciones
from financiero.servicios import registrar_pago,reservar_recibo
from financiero.models import (ConceptoCobro,Obligacion,Pago,Ingreso,Egreso,Donacion,Beca,
    SolicitudBeca,SolicitudPadrinazgo,Donante,ConvenioPago,CuotaConvenio,Caja,MovimientoCaja,
    SolicitudEgreso,RecepcionDonacion)

D=Decimal
CERO=D('0.00')


def verificar_memoria():
    db=settings.DATABASES.get('default',{})
    if (db.get('ENGINE')!='django.db.backends.sqlite3' or db.get('NAME')!=':memory:' or
        connection.vendor!='sqlite' or connection.settings_dict['NAME']!=':memory:'):
        raise RuntimeError('Simulación abortada: se exige SQLite :memory: exactamente.')


def mes(fecha,desplazamiento):
    n=fecha.year*12+fecha.month-1+desplazamiento
    return date(n//12,n%12+1,1)


class Escenario:
    def __init__(self,semilla,referencia):
        self.semilla=semilla;self.referencia=referencia;self.inicio=mes(referencia,-2)
        self.fin=mes(self.inicio,6)-timedelta(days=1)
        self.azar=random.Random(semilla);self.serial=0;self.eventos=[];self.dinero=[]
        self.cargos={};self.padrinazgos=[];self.contratos=[];self.cierres=[];self.notas={}
        self.credenciales=[];self.password=secrets.token_urlsafe(18);self.usuarios={}
        self.reloj=timezone.make_aware(datetime.combine(self.inicio,time(12)))
        self.resumen={}

    def clave(self):
        self.serial+=1
        return uuid5(NAMESPACE_URL,f'vidasys-f71-{self.semilla}-{self.referencia}-{self.serial}')

    def agendar(self,dia,fn,prioridad=10):
        fecha=self.inicio+timedelta(days=dia)
        if fecha<=self.referencia:self.eventos.append((fecha,prioridad,len(self.eventos),fn))

    @contextmanager
    def reloj_acotado(self):
        escenario=self
        class FechaSimulada(datetime):
            @classmethod
            def now(cls,tz=None):
                return escenario.reloj.astimezone(tz) if tz else escenario.reloj.replace(tzinfo=None)
        # También alcanza defaults de modelos que conservaron la función timezone.now original.
        with patch.object(timezone,'datetime',FechaSimulada):yield

    def usuario(self,nombre,rol):
        u=Usuario.objects.create_user(nombre,nombre+'@example.test',self.password,rol=rol,
            debe_cambiar_password=False,is_staff=rol=='ADMINISTRADOR',is_superuser=rol=='ADMINISTRADOR')
        self.credenciales.append(nombre);return u

    def catalogos(self):
        for rol in ('SECRETARIA','DIRECTORA','ADMINISTRADOR','PASTOR_PRINCIPAL'):
            self.usuarios[rol]=self.usuario('sim-'+rol.lower().replace('_','-'),rol)
        self.secretaria=self.usuarios['SECRETARIA'];self.directora=self.usuarios['DIRECTORA'];self.admin=self.usuarios['ADMINISTRADOR']
        self.maestros=[]
        for n in range(6):
            u=self.usuario(f'sim-maestro-{n+1:02}','MAESTRO')
            self.maestros.append(Maestro.objects.create(usuario=u,nombres=f'Docente simulado {n+1}',apellidos='Ensayo',pais='SV',estado='ACTIVO'))
        conceptos=[ConceptoCobro.objects.create(nombre=n,estado='ACTIVO',permite_abonos=n=='MENSUALIDAD') for n in ('MATRICULA','MENSUALIDAD')]
        self.ciclos=[];self.cursos=[]
        nombres=['Panorama bíblico','Hermenéutica','Historia de la iglesia','Vida comunitaria','Ética ministerial','Práctica formativa']
        for nivel,numero in enumerate((1,3),1):
            c=CicloAcademico.objects.create(nombre=f'Simulación · Año {nivel} · Ciclo {numero}',numero_ciclo=numero,
                anio=self.inicio.year,fecha_inicio=self.inicio,fecha_fin=self.fin,estado='ACTIVO')
            self.ciclos.append(c)
            calendario.guardar(c,dict(emision=str(self.inicio),matricula=str(self.inicio+timedelta(days=9)),
                meses=[mes(self.inicio,n).strftime('%Y-%m') for n in range(1,6)],
                concepto_matricula=conceptos[0].pk,concepto_mensualidad=conceptos[1].pk))
            for n,nombre in enumerate(nombres):
                m=Materia.objects.create(codigo_materia=f'SIM-{numero}-{n+1}',nombre=f'{nombre} · nivel {nivel}',numero_ciclo_formativo=numero,estado='ACTIVA')
                curso=Curso.objects.create(materia=m,maestro=self.maestros[n],ciclo=c,fecha_inicio=self.inicio,
                    fecha_fin=self.fin,modalidad='PRESENCIAL',estado='ACTIVO')
                self.cursos.append(curso)
                inicio=self.inicio+timedelta(days=7 if n<3 else 55)
                propuesta=flujo.propuesta(inicio,'semanal',time(8+n),60)
                flujo.guardar_calendario(curso.pk,curso.maestro.usuario,propuesta,flujo.firma_calendario(curso,[]))
        self.estudiantes=[];self.matriculas=[];self.obligaciones=[]
        nombres=['Alba','Bruno','Celia','Darío','Elena','Fabián','Gala','Hugo','Iris','Joel','Kiara','Leo','Mara','Nilo','Olga','Pablo','Rita','Saúl','Tania','Ulises']
        apellidos=['Amanecer','Bosque','Cauce','Duna','Estrella','Faro','Granito','Horizonte']
        self.azar.shuffle(nombres)
        for n in range(40):
            u=self.usuario(f'sim-estudiante-{n+1:02}','ESTUDIANTE')
            e=Estudiante.objects.create(usuario=u,codigo_estudiante=f'SIM-{n+1:03}',
                nombres=nombres[n%20]+' Ficticio',apellidos=apellidos[n%8]+' Ensayo',fecha_ingreso=self.inicio,estado='ACTIVO')
            m,_,_=flujo.matricular(estudiante=e,ciclo=self.ciclos[n//20],numero_matricula=f'SIM-M{n+1:03}',fecha_matricula=self.inicio)
            obs=list(m.obligaciones.order_by('pk'));self.estudiantes.append(e);self.matriculas.append(m);self.obligaciones.append(obs)
            for o in obs:self.cargos[o.pk]=dict(estudiante=n,original=D('20'),descuento=CERO,vencimiento=o.fecha_vencimiento)
        self.donantes=[]
        for n in range(5):
            self.donantes.append(aportes.guardar_donante(usuario=self.secretaria,clave=self.clave(),tipo='PERSONA',
                nombre_completo=f'Donante ficticio {n+1}',documento_identidad='',correo=f'donante{n+1}@example.test',telefono='',
                pais='SV',direccion='',es_anonimo=n==4,notas='Solo simulación',estado='ACTIVO'))
        self.categorias_ingreso=[operaciones.configurar_categoria(usuario=self.admin,tipo='INGRESO',nombre=n) for n in ('Librería','Certificaciones','Cafetería')]
        self.categorias_egreso=[operaciones.configurar_categoria(usuario=self.admin,tipo='EGRESO',nombre=n) for n in ('Servicios','Material didáctico','Mantenimiento')]

    def efectivo(self,tipo,importe,metodo,origen,apps=(),**extra):
        r=dict(tipo=tipo,importe=D(importe),metodo=metodo,origen=origen,apps=list(apps),vigente=True,fecha=timezone.localdate(),**extra)
        self.dinero.append(r);return r

    def pago(self,n,k,importe,anular=False):
        o=self.obligaciones[n][k];importe=D(importe);metodo='TRANSFERENCIA' if (n+k)%3==0 else 'EFECTIVO'
        p,_=registrar_pago(usuario=self.secretaria,estudiante=self.estudiantes[n],token=reservar_recibo(self.secretaria,self.estudiantes[n]),
            metodo=metodo,referencia=str(self.clave()),aplicaciones=[(o.pk,importe)])
        r=self.efectivo('PAGO',importe,metodo,'MATRICULA' if k==0 else 'MENSUALIDAD',[(o.pk,importe)],pk=p.pk)
        if anular:
            s=anulaciones.solicitar(usuario=self.secretaria,pago_id=p.pk,clave=self.clave(),motivo='Ensayo: recibo capturado por error')
            revision=anulaciones.previsualizar(usuario=self.directora,solicitud_id=s.pk)
            anulaciones.resolver(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA',revision=revision)
            r['vigente']=False

    def beca(self,n):
        porcentaje='100' if n%2==0 else '50';conceptos=['MATRICULA'] if n in (20,22) else ['MATRICULA','MENSUALIDAD']
        ids=[o.pk for o in self.obligaciones[n] if o.concepto.nombre in conceptos]
        s=becas.solicitar(usuario=self.secretaria,matricula_id=self.matriculas[n].pk,porcentaje=porcentaje,conceptos=conceptos,
            alcance='AMBAS',justificacion='Apoyo ficticio para simulación',clave=self.clave())
        d=dict(usuario=self.directora,solicitud_id=s.pk,porcentaje=porcentaje,conceptos=conceptos,alcance='AMBAS',obligaciones=ids,observaciones='Autorización ficticia')
        _,rev=becas.previsualizar(**d);becas.resolver(**d,decision='APROBADA',revision=rev)
        for pk in ids:self.cargos[pk]['descuento']=D('20')*D(porcentaje)/100

    def padrinazgo(self,n):
        obs=self.obligaciones[n][1:] if n in (20,22) else self.obligaciones[n]
        monto=D('10') if n in (22,29,34) else D('20')
        inicio=self.inicio+timedelta(days=2) if n!=35 else self.referencia+timedelta(days=7)
        limite=self.inicio+timedelta(days=35) if n==32 else self.fin
        s=aportes.solicitar(usuario=self.secretaria,clave=self.clave(),donante_id=self.donantes[n%5].pk,
            matricula_id=self.matriculas[n].pk,inicio=inicio,limite=limite,modalidad='FIJO',
            asignaciones=[(o.pk,monto) for o in obs],observaciones='Compromiso ficticio, no ingreso')
        datos=dict(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA')
        rev=aportes.resolver(**datos);s=aportes.resolver(**datos,revision=rev,confirmar=True)
        self.padrinazgos.append(dict(n=n,solicitud=s,inicio=inicio,limite=limite,lineas=[(o.pk,monto) for o in obs]))

    def donacion(self,n=None,importe='12',anular=False):
        s=next((s for s in self.padrinazgos if s['n']==n),None)
        apps=[];modalidad='GENERAL'
        if s:
            modalidad='PADRINAZGO';apps=[(pk,monto if n==31 else monto/2 if n in (30,34) else monto) for pk,monto in s['lineas']]
            if n==33:apps=apps[:1]
            importe=sum(m for _,m in apps)
        elif n is not None:
            modalidad='DIRIGIDA';apps=[(self.obligaciones[n][-1].pk,D(importe))]
        datos=dict(usuario=self.secretaria,clave=self.clave(),donante_id=(s['solicitud'].donante_id if s else self.donantes[self.serial%5].pk),modalidad=modalidad,
            monto=importe,fecha=timezone.now(),metodo='TRANSFERENCIA' if self.serial%3==0 else 'EFECTIVO',referencia=str(self.clave()))
        if n is not None:datos.update(matricula_id=self.matriculas[n].pk,asignaciones=apps)
        if s:datos['solicitud_id']=s['solicitud'].pk
        r=aportes.recibir(**datos)
        libro=self.efectivo('DONACION',importe,datos['metodo'],'DON_'+modalidad,apps,pk=r.pk,padrinazgo=n if s else None)
        if anular:
            a=aportes.pedir_anulacion(usuario=self.secretaria,recepcion_id=r.pk,clave=self.clave(),motivo='Ensayo de anulación de aporte')
            d=dict(usuario=self.directora,anulacion_id=a.pk,decision='APROBADA')
            rev=aportes.anular(**d);aportes.anular(**d,revision=rev,confirmar=True);libro['vigente']=False

    def convenio(self,n):
        ids=[o.pk for o in self.obligaciones[n]]
        dias=[20,60,100] if n!=39 else [(self.referencia-self.inicio).days+10,120,150]
        cuotas=[dict(fecha=str(self.inicio+timedelta(days=d)),monto='40') for d in dias]
        s=convenios.solicitar(usuario=self.secretaria,estudiante_id=self.estudiantes[n].pk,obligaciones=ids,
            cuotas=cuotas,justificacion='Plan ficticio',clave=self.clave())
        d=dict(usuario=self.directora,solicitud_id=s.pk,obligaciones=ids,cuotas=cuotas)
        _,rev=convenios.previsualizar(**d);s=convenios.resolver(**d,decision='APROBADA',revision=rev)
        self.contratos.append(dict(n=n,modelo=s.convenio,fechas=[self.inicio+timedelta(days=d) for d in dias],abonado=CERO))

    def abono(self,n):
        c=next(c for c in self.contratos if c['n']==n);q=list(c['modelo'].cuotas.order_by('numero_cuota'))
        apps=[(o.pk,D('20')) for o in (self.obligaciones[n] if n==37 else self.obligaciones[n][:2])]
        cuotas=[(x.pk,D('40')) for x in (q if n==37 else q[:1])]
        metodo='EFECTIVO' if n==37 else 'TRANSFERENCIA'
        p,_=convenios.registrar_abono(usuario=self.secretaria,convenio_id=c['modelo'].pk,token=reservar_recibo(self.secretaria,self.estudiantes[n]),
            metodo=metodo,referencia=str(self.clave()),cuotas=cuotas,obligaciones=apps)
        total=sum(m for _,m in apps);c['abonado']+=total
        self.efectivo('PAGO',total,metodo,'CONVENIO',apps,pk=p.pk)

    def ingreso(self,n):
        metodo='TRANSFERENCIA' if n%3==0 else 'EFECTIVO';monto=D(10+n)
        r=operaciones.registrar_ingreso(usuario=self.secretaria,clave=self.clave(),categoria_id=self.categorias_ingreso[n%3].pk,
            concepto=f'Actividad institucional ficticia {n+1}',origen='Simulación',monto=monto,metodo=metodo,referencia=str(self.clave()),fecha=timezone.now())
        libro=self.efectivo('INGRESO',monto,metodo,'ADMINISTRATIVO',pk=r.pk)
        if n==2:
            s=operaciones.solicitar_anulacion(usuario=self.secretaria,tipo='INGRESO',registro_id=r.pk,clave=self.clave(),motivo='Error ficticio')
            d=dict(usuario=self.directora,solicitud_id=s.pk,decision='APROBADA');rev=operaciones.decidir_anulacion(**d)
            operaciones.decidir_anulacion(**d,revision=rev,confirmar=True);libro['vigente']=False

    def egreso(self,n):
        s=operaciones.solicitar_egreso(usuario=self.secretaria,clave=self.clave(),categoria_id=self.categorias_egreso[n%3].pk,
            concepto=f'Compra ficticia {n+1}',beneficiario=f'Proveedor ficticio {n%4+1}',monto=D(5+n),justificacion='Necesidad del ensayo')
        if n>=12:return
        decision='RECHAZADA' if n==11 else 'APROBADA'
        operaciones.decidir_egreso(usuario=self.directora,solicitud_id=s.pk,decision=decision,resolucion='Resolución ficticia de ensayo')
        if n>=10:return
        metodo='TRANSFERENCIA' if n%3==0 else 'EFECTIVO'
        r=operaciones.desembolsar(usuario=self.secretaria,clave=self.clave(),solicitud_id=s.pk,metodo=metodo,referencia=str(self.clave()),fecha=timezone.now())
        libro=self.efectivo('EGRESO',D(5+n),metodo,'EGRESO',pk=r.pk)
        if n==4:
            a=operaciones.solicitar_anulacion(usuario=self.secretaria,tipo='EGRESO',registro_id=r.pk,clave=self.clave(),motivo='Anulación administrativa, sin recuperación física')
            d=dict(usuario=self.directora,solicitud_id=a.pk,decision='APROBADA');rev=operaciones.decidir_anulacion(**d)
            operaciones.decidir_anulacion(**d,revision=rev,confirmar=True);libro['vigente']=False

    def abrir(self):
        self.caja=caja.abrir(usuario=self.secretaria,clave=self.clave(),fondo='100')
        self.libro_caja_inicio=len(self.dinero)

    def cerrar(self,n):
        movimientos=self.dinero[self.libro_caja_inicio:]
        esperado=D('100')+sum((r['importe']*(-1 if r['tipo']=='EGRESO' else 1) for r in movimientos if r['metodo']=='EFECTIVO'),CERO)
        diferencia=D('1') if n%3==0 else CERO
        d=dict(usuario=self.secretaria,caja_id=self.caja.pk,contado=esperado+diferencia,observaciones='Diferencia ficticia de conteo justificada' if diferencia else 'Conteo ficticio cuadrado')
        _,rev=caja.preparar_cierre(**d);caja.cerrar(**d,revision=rev)
        self.cierres.append(dict(pk=self.caja.pk,esperado=esperado,diferencia=diferencia))

    def sesion(self,curso,n):
        s=SesionClase.objects.get(curso=curso,numero_clase=n)
        if s.estado in ('SUSPENDIDA','CANCELADA'):return
        flujo.actualizar_sesion(curso.pk,s.pk,curso.maestro.usuario,
            dict(fecha=s.fecha,hora_inicio=s.hora_inicio,hora_fin=s.hora_fin,estado='IMPARTIDA'),
            flujo.firma_calendario(curso,list(curso.sesiones.order_by('numero_clase'))))
        for i in InscripcionCurso.objects.filter(curso=curso).select_related('matricula').order_by('pk'):
            if i.estado!='CURSANDO':continue
            numero=int(i.matricula.numero_matricula[-3:])-1
            estado='AUSENTE_INJUSTIFICADA' if numero%13==0 and n in (5,6) else 'AUSENTE_JUSTIFICADA' if numero%7==0 and n==2 else 'PRESENTE'
            Asistencia.objects.create(inscripcion=i,sesion=s,estado_asistencia=estado,observaciones='Registro ficticio de ensayo')

    def notas_y_cierre(self,curso):
        for i in InscripcionCurso.objects.filter(curso=curso).select_related('matricula').order_by('pk'):
            if i.estado!='CURSANDO':continue
            n=int(i.matricula.numero_matricula[-3:])-1
            nota=D(55+(n*7+curso.pk)%41)
            componentes={c:(limite*nota/100 if k<4 else CERO if k==4 else nota).quantize(D('.01')) for k,(c,limite) in enumerate(Calificacion.LIMITES_COMPONENTES.items())}
            cal=Calificacion(inscripcion=i,observaciones='Evaluación ficticia',**componentes);cal.save()
            self.notas[i.pk]=nota
        curso.refresh_from_db()
        flujo.cerrar_curso(curso.pk,curso.maestro.usuario,flujo.firma_cierre(curso,list(curso.sesiones.order_by('numero_clase'))))

    def extra(self,curso):
        flujo.autorizar_extra(SesionClase(curso=curso,numero_clase=7,fecha=self.inicio+timedelta(days=49),hora_inicio=time(16),hora_fin=time(17),estado='PROGRAMADA',motivo_extension='Refuerzo ficticio autorizado'),self.directora)

    def cancelacion(self,curso,aprobar):
        s=curso.sesiones.get(numero_clase=6)
        pedido=solicitudes.solicitar(sesion_id=s.pk,usuario=curso.maestro.usuario,motivo='Actividad ficticia reprogramada institucionalmente',clave=self.clave())
        if aprobar:solicitudes.decidir(solicitud_id=pedido.pk,usuario=self.directora,decision='APROBADA')

    def correccion(self,aprobar=True):
        curso=Curso.objects.get(pk=self.cursos[0].pk)
        i=InscripcionCurso.objects.filter(curso=curso,estado='APROBADA').select_related('calificacion').order_by('pk')[0 if aprobar else 1]
        nota=i.calificacion;componentes={c:getattr(nota,c) for c in Calificacion.COMPONENTES};componentes['tarea_1']=D('100')
        s=correcciones.solicitar_correccion(inscripcion_id=i.pk,usuario=curso.maestro.usuario,motivo='Revisión ficticia de tarea',clave=self.clave(),componentes=componentes,revision=correcciones.firma_nota(curso,i,nota))
        if not aprobar:return
        solicitudes.decidir(solicitud_id=s.pk,usuario=self.directora,decision='APROBADA')
        self.notas[i.pk]=(sum(componentes[c] for c in Calificacion.COMPONENTES[:5])+sum(componentes[c] for c in Calificacion.COMPONENTES[5:]))/5

    def solicitudes_pendientes(self):
        becas.solicitar(usuario=self.secretaria,matricula_id=self.matriculas[17].pk,porcentaje='50',
            conceptos=['MENSUALIDAD'],alcance='AMBAS',justificacion='Pendiente de revisión ficticia',clave=self.clave())
        obs=self.obligaciones[16][-2:]
        aportes.solicitar(usuario=self.secretaria,clave=self.clave(),donante_id=self.donantes[0].pk,
            matricula_id=self.matriculas[16].pk,inicio=timezone.localdate(),limite=self.fin,modalidad='FIJO',
            asignaciones=[(o.pk,D('10')) for o in obs],observaciones='Pendiente: no protege ni ingresa dinero')
        convenios.solicitar(usuario=self.secretaria,estudiante_id=self.estudiantes[14].pk,
            obligaciones=[o.pk for o in self.obligaciones[14][3:]],
            cuotas=[dict(fecha=str(self.referencia+timedelta(days=15)),monto='60')],
            justificacion='Convenio pendiente ficticio',clave=self.clave())
        self.correccion(aprobar=False)

    def suspender(self):
        curso=self.cursos[3];s=curso.sesiones.get(numero_clase=6)
        flujo.actualizar_sesion(curso.pk,s.pk,curso.maestro.usuario,
            dict(fecha=s.fecha,hora_inicio=s.hora_inicio,hora_fin=s.hora_fin,estado='SUSPENDIDA'),
            flujo.firma_calendario(curso,list(curso.sesiones.order_by('numero_clase'))))

    def planificar(self):
        self.agendar(1,self.abrir,0)
        for n in range(20,28):self.agendar(2,lambda n=n:self.beca(n))
        for n in [*range(28,36),20,22]:self.agendar(3,lambda n=n:self.padrinazgo(n))
        for n in range(36,40):self.agendar(4,lambda n=n:self.convenio(n))
        for n in range(20):
            if n<8:
                for k in range(6):self.agendar(5+k*12,lambda n=n,k=k:self.pago(n,k,'20'))
            elif n<16:
                for k in range(3):self.agendar(5+k*12,lambda n=n,k=k:self.pago(n,k,'20'))
            else:
                self.agendar(5,lambda n=n:self.pago(n,0,'20'))
                for k in range(1,4):
                    for parte in range(2):self.agendar(5+k*12+parte,lambda n=n,k=k,parte=parte:self.pago(n,k,'5',anular=n>=18 and k==1 and parte==0))
        for n in (21,23,25,27):
            for k in range(6):self.agendar(6+k*12,lambda n=n,k=k:self.pago(n,k,'10'))
        for k in range(6):self.agendar(7+k*12,lambda k=k:self.pago(29,k,'10'))
        for n in (37,38):self.agendar(18,lambda n=n:self.abono(n))
        for n in (30,31,33,34):self.agendar(22,lambda n=n:self.donacion(n))
        for n in range(9):self.agendar(8+n*7,lambda n=n:self.donacion(importe=str(10+n),anular=n==1))
        self.agendar(36,lambda:self.donacion(15,importe='8'))
        for n in range(18):self.agendar(5+n*4,lambda n=n:self.ingreso(n))
        for n in range(15):self.agendar(6+n*4,lambda n=n:self.egreso(n))
        for n in range(10):
            self.agendar(7+n*7,lambda n=n:self.cerrar(n),90)
            self.agendar(8+n*7,self.abrir,0)
        # Caja propia abierta de Administración, sin inventar movimientos.
        self.agendar(75,lambda:caja.abrir(usuario=self.admin,clave=self.clave(),fondo='50'))
        for j,c in enumerate(self.cursos):
            finales=j%6<3
            for k in range(1,7):self.agendar((7 if finales else 55)+(k-1)*7,lambda c=c,k=k:self.sesion(c,k))
            if j%6==0:
                self.agendar(2,lambda c=c:self.extra(c))
                self.agendar(49,lambda c=c:self.sesion(c,7))
            if finales:self.agendar(51,lambda c=c:self.notas_y_cierre(c))
        self.agendar(60,self.correccion)
        self.agendar(76,lambda:self.cancelacion(self.cursos[5],True))
        self.agendar(76,lambda:self.cancelacion(self.cursos[4],False))
        self.agendar((self.referencia-self.inicio).days,self.solicitudes_pendientes,85)
        self.agendar(77,self.suspender)
        # Notas provisionales en materias activas después de las sesiones impartidas.
        self.agendar((self.referencia-self.inicio).days,self.notas_provisionales,80)

    def notas_provisionales(self):
        for i in InscripcionCurso.objects.filter(curso__estado='ACTIVO',estado='CURSANDO').select_related('curso'):
            if i.pk%3==0:
                componentes={c:limite*D('.8') if k<4 else CERO if k==4 else D('80') for k,(c,limite) in enumerate(Calificacion.LIMITES_COMPONENTES.items())}
                Calificacion(inscripcion=i,observaciones='Provisional ficticia, curso activo',**componentes).save()

    def esperados(self):
        vigentes=[r for r in self.dinero if r['vigente']]
        ingresos=sum((r['importe'] for r in vigentes if r['tipo']!='EGRESO'),CERO)
        egresos=sum((r['importe'] for r in vigentes if r['tipo']=='EGRESO'),CERO)
        pagos=Counter();donaciones=Counter()
        for r in vigentes:
            destino=pagos if r['tipo']=='PAGO' else donaciones if r['tipo']=='DONACION' else None
            if destino is not None:
                for pk,monto in r['apps']:destino[pk]+=monto
        saldos={pk:max(c['original']-c['descuento']-pagos[pk]-donaciones[pk],CERO) for pk,c in self.cargos.items()}
        reservas=Counter();protegidos=Counter();pad=[]
        for s in self.padrinazgos:
            recibido=Counter()
            for r in vigentes:
                if r.get('padrinazgo')==s['n']:
                    for pk,m in r['apps']:recibido[pk]+=m
            pendiente=sum((max(m-recibido[pk],CERO) for pk,m in s['lineas']),CERO)
            for pk,m in s['lineas']:
                resto=max(m-recibido[pk],CERO);reservas[pk]+=resto
                if s['inicio']<=self.referencia:protegidos[pk]+=resto
            pad.append(dict(n=s['n'],comprometido=sum(m for _,m in s['lineas']),recibido=sum(recibido.values(),CERO),pendiente=pendiente,vencido=s['limite']<self.referencia))
        cobertura={pk:min(saldos[pk],protegidos[pk]) for pk in saldos}
        conv_ids={o.pk for c in self.contratos for o in self.obligaciones[c['n']]}
        en_convenio=sum((saldos[pk]-cobertura[pk] for pk in conv_ids),CERO)
        saldo=sum(saldos.values(),CERO);proteccion=sum(cobertura.values(),CERO)
        return dict(ingresos=ingresos,egresos=egresos,resultado=ingresos-egresos,original=D('4800'),
            descuentos=sum((c['descuento'] for c in self.cargos.values()),CERO),saldo=saldo,cobertura=proteccion,
            cargo_estudiantes=saldo-proteccion,en_convenio=en_convenio,directo=saldo-proteccion-en_convenio,
            compromisos_pendientes=sum(reservas.values(),CERO),becas=sum((c['descuento'] for c in self.cargos.values()),CERO),
            padrinazgos=pad,anulados=sum((r['importe'] for r in self.dinero if not r['vigente']),CERO),
            saldos=saldos,coberturas=cobertura)


def generar(*,semilla=711,referencia=None):
    verificar_memoria()
    if any(m.objects.exists() for m in (Usuario,Estudiante,Matricula,Pago,Ingreso,Egreso,Obligacion)):
        raise RuntimeError('La simulación exige una base efímera vacía; no mezcla ni elimina datos existentes.')
    referencia=referencia or timezone.localdate()
    t=perf_counter();e=Escenario(semilla,referencia)
    with transaction.atomic(),e.reloj_acotado():
        e.catalogos();e.planificar()
        for fecha,_,_,accion in sorted(e.eventos,key=lambda x:x[:3]):
            e.reloj=timezone.make_aware(datetime.combine(fecha,time(12)))
            accion()
        e.reloj=timezone.make_aware(datetime.combine(referencia,time(18)))
        e.resumen={m._meta.db_table:m.objects.count() for m in (Usuario,Estudiante,Maestro,Materia,CicloAcademico,Curso,Matricula,
            InscripcionCurso,SesionClase,Asistencia,Calificacion,SolicitudAcademica,Obligacion,Pago,Ingreso,Egreso,Donacion,
            Donante,Beca,SolicitudBeca,SolicitudPadrinazgo,ConvenioPago,CuotaConvenio,SolicitudEgreso,RecepcionDonacion,MovimientoCaja)}
        e.resumen.update(estudiantes_por_anio={'primero':20,'segundo':20},cajas_cerradas=Caja.objects.filter(estado='CERRADA').count(),
            cajas_abiertas=Caja.objects.filter(estado='ABIERTA').count(),cursos_por_estado=dict(Counter(Curso.objects.values_list('estado',flat=True))),
            convenios_por_estado=dict(Counter(ConvenioPago.objects.values_list('estado',flat=True))),
            solicitudes_egreso_por_estado=dict(Counter(SolicitudEgreso.objects.values_list('estado',flat=True))),
            sesiones_por_estado=dict(Counter(SesionClase.objects.values_list('estado',flat=True))),
            asistencias_por_estado=dict(Counter(Asistencia.objects.values_list('estado_asistencia',flat=True))),
            resultados_academicos=dict(Counter(InscripcionCurso.objects.values_list('estado',flat=True))),
            generacion_segundos=round(perf_counter()-t,3),semilla=semilla,referencia=str(referencia))
        import hashlib,json
        huella={'nombres':[(x.codigo_estudiante,x.nombres,x.apellidos) for x in e.estudiantes],
            'libro':e.dinero,'cargos':e.cargos,'notas':e.notas}
        e.resumen['huella_datos_sha256']=hashlib.sha256(json.dumps(huella,sort_keys=True,default=str).encode()).hexdigest()
    return e
