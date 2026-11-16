"""Permisos, filtros, importes y exportación; solo SQLite y datos ficticios."""
import csv
import io
from datetime import date, datetime, time
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academico.models import (Asistencia, Calificacion, CicloAcademico, Curso, Estudiante,
                             InscripcionCurso, Maestro, Materia, Matricula, SesionClase)
from core.models import Usuario
from financiero.models import CategoriaIngreso, DetallePago, Ingreso, Obligacion, Pago, ConceptoCobro
from .catalogo import CATALOGO
from .consultas import generar


class ReportesInstitucionalesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios={rol:Usuario.objects.create_user('rep-'+rol,rol+'@example.test','Ficticia-Reporte-72!',rol=rol) for rol in
            ('ADMINISTRADOR','DIRECTORA','SECRETARIA','MAESTRO','ESTUDIANTE','PASTOR_PRINCIPAL')}
        otro=Usuario.objects.create_user('docente-ajeno-reportes','otro-doc@example.test','Ficticia-Doc-72!',rol='MAESTRO')
        maestro=Maestro.objects.create(usuario=cls.usuarios['MAESTRO'],nombres='Docente ficticio propio',apellidos='Prueba',pais='SV',estado='ACTIVO')
        ajeno=Maestro.objects.create(usuario=otro,nombres='Docente ficticio ajeno',apellidos='Prueba',pais='SV',estado='ACTIVO')
        cls.ciclo=CicloAcademico.objects.create(nombre='Ciclo I de prueba',numero_ciclo=1,anio=2026,fecha_inicio='2026-01-01',fecha_fin='2026-06-30',estado='ACTIVO')
        cls.segundo=CicloAcademico.objects.create(nombre='Ciclo II de prueba',numero_ciclo=2,anio=2026,fecha_inicio='2026-07-01',fecha_fin='2026-12-31',estado='ACTIVO')
        cls.ciclo.refresh_from_db();cls.segundo.refresh_from_db()
        cursos=[]
        for n,ciclo,docente in [(1,cls.ciclo,maestro),(2,cls.ciclo,ajeno),(3,cls.segundo,maestro)]:
            materia=Materia.objects.create(codigo_materia=f'REP-MAT-{n}',nombre=f'Materia ficticia {n}',numero_ciclo_formativo=ciclo.numero_ciclo,estado='ACTIVA')
            cursos.append(Curso.objects.create(materia=materia,maestro=docente,ciclo=ciclo,fecha_inicio=ciclo.fecha_inicio,fecha_fin=ciclo.fecha_fin,modalidad='PRESENCIAL',estado='ACTIVO'))
        cls.curso,cls.ajeno,cls.curso_segundo=cursos
        cls.estudiante=Estudiante.objects.create(codigo_estudiante='REPORTE-PROPIO',nombres='Persona ficticia propia',apellidos='Prueba',fecha_ingreso='2026-01-01',estado='ACTIVO')
        cls.otro=Estudiante.objects.create(codigo_estudiante='RESERVADO-AJENO',nombres='Persona ficticia ajena',apellidos='Prueba',fecha_ingreso='2026-01-01',estado='ACTIVO')
        cls.matricula=Matricula.objects.create(estudiante=cls.estudiante,ciclo=cls.ciclo,numero_matricula='REP-M1',fecha_matricula='2026-01-02',estado='ACTIVA')
        cls.matricula2=Matricula.objects.create(estudiante=cls.estudiante,ciclo=cls.segundo,numero_matricula='REP-M2',fecha_matricula='2026-07-02',estado='ACTIVA')
        mat_ajena=Matricula.objects.create(estudiante=cls.otro,ciclo=cls.ciclo,numero_matricula='RESERVADA-MATRICULA',fecha_matricula='2026-01-03',estado='ACTIVA')
        cls.inscripcion=InscripcionCurso.objects.create(matricula=cls.matricula,curso=cls.curso,fecha_inscripcion='2026-01-02',estado='CURSANDO')
        cls.inscripcion2=InscripcionCurso.objects.create(matricula=cls.matricula2,curso=cls.curso_segundo,fecha_inscripcion='2026-07-02',estado='CURSANDO')
        cls.insc_ajena=InscripcionCurso.objects.create(matricula=mat_ajena,curso=cls.ajeno,fecha_inscripcion='2026-01-03',estado='CURSANDO')
        cls.sesion=SesionClase.objects.create(curso=cls.curso,numero_clase=1,fecha='2026-02-10',hora_inicio=time(8),hora_fin=time(9),estado='IMPARTIDA')
        Asistencia.objects.create(inscripcion=cls.inscripcion,sesion=cls.sesion,estado_asistencia='PRESENTE')
        Calificacion.objects.create(inscripcion=cls.inscripcion,**dict(zip(Calificacion.COMPONENTES,[40,20,20,20,0,80,80,80,80])))
        concepto=ConceptoCobro.objects.create(nombre='MENSUALIDAD',permite_abonos=True,estado='ACTIVO')
        cls.obligacion=Obligacion.objects.create(matricula=cls.matricula,concepto=concepto,descripcion='Cargo ficticio primero',fecha_emision='2026-01-01',fecha_vencimiento='2026-02-10',monto_original='40',monto_descuento='5',estado='PENDIENTE')
        cls.obligacion2=Obligacion.objects.create(matricula=cls.matricula2,concepto=concepto,descripcion='Cargo ficticio segundo',fecha_emision='2026-07-01',fecha_vencimiento='2026-08-10',monto_original='50',monto_descuento='0',estado='PENDIENTE')
        cls.obligacion.refresh_from_db();cls.obligacion2.refresh_from_db()
        cuando=timezone.make_aware(datetime(2026,2,10,12))
        cls.pago=Pago.objects.create(estudiante=cls.estudiante,usuario=cls.usuarios['SECRETARIA'],numero_recibo='REPORTE-RECIBO',fecha_pago=cuando,monto_total='30',metodo_pago='EFECTIVO',estado='REGISTRADO')
        DetallePago.objects.create(pago=cls.pago,obligacion=cls.obligacion,monto_aplicado='10')
        DetallePago.objects.create(pago=cls.pago,obligacion=cls.obligacion2,monto_aplicado='20')
        anulado=Pago.objects.create(estudiante=cls.estudiante,usuario=cls.usuarios['SECRETARIA'],numero_recibo='NO-CONTAR-ANULADO',fecha_pago=cuando,monto_total='15',metodo_pago='EFECTIVO',estado='ANULADO')
        DetallePago.objects.create(pago=anulado,obligacion=cls.obligacion,monto_aplicado='15')
        categoria=CategoriaIngreso.objects.create(nombre='Ingreso ficticio',estado='ACTIVO')
        for estado,monto in [('REGISTRADO','70'),('ANULADO','100')]:
            Ingreso.objects.create(categoria_ingreso=categoria,usuario_registra=cls.usuarios['SECRETARIA'],fecha_ingreso=cuando,monto=monto,
                metodo_pago='EFECTIVO',estado=estado,fecha_creacion=cuando)

    def login(self,rol='ADMINISTRADOR'):self.client.force_login(self.usuarios[rol])

    def url(self,tipo):return reverse('reportes_consultar',args=[tipo])

    def test_permisos_por_reporte_y_formatos(self):
        self.assertEqual(self.client.get(reverse('reportes')).status_code,302)
        for rol,usuario in self.usuarios.items():
            self.client.force_login(usuario)
            for tipo,(_,roles,_) in CATALOGO.items():
                with self.subTest(rol=rol,tipo=tipo):
                    self.assertEqual(self.client.get(self.url(tipo)).status_code,200 if rol in roles else 403)
        for rol,tipo in [('SECRETARIA','calificaciones'),('MAESTRO','pagos'),('ESTUDIANTE','matriculas'),('PASTOR_PRINCIPAL','resumen')]:
            self.login(rol)
            for formato in ('csv','imprimir'):self.assertEqual(self.client.get(self.url(tipo),{'formato':formato}).status_code,403)
        with self.assertRaises(PermissionDenied):generar('pagos',self.usuarios['MAESTRO'],{})

    def test_docente_solo_cursos_propios_y_filtros_adulterados(self):
        self.login('MAESTRO')
        for tipo in ('inscripciones','calificaciones','asistencia','estados'):
            respuesta=self.client.get(self.url(tipo))
            self.assertContains(respuesta,'REPORTE-PROPIO')
            self.assertNotContains(respuesta,'RESERVADO-AJENO')
            self.assertEqual(self.client.get(self.url(tipo),{'curso':self.ajeno.pk}).status_code,400)
            self.assertEqual(self.client.get(self.url(tipo),{'estudiante':self.otro.pk,'formato':'csv'}).status_code,400)
        respuesta=self.client.get(self.url('calificaciones'),{'formato':'csv'})
        self.assertNotIn('RESERVADO-AJENO',respuesta.content.decode())

    def test_filtros_ciclo_curso_estudiante_y_fechas(self):
        self.login()
        respuesta=self.client.get(self.url('matriculas'),{'ciclo':self.ciclo.pk,'curso':self.curso.pk,'estudiante':self.estudiante.pk,'desde':'2026-01-01','hasta':'2026-01-02'})
        self.assertEqual(len(respuesta.context['filas']),1)
        self.assertContains(respuesta,'REP-M1');self.assertNotContains(respuesta,'REP-M2')
        respuesta=self.client.get(self.url('asistencia'),{'desde':'2026-03-01'})
        self.assertContains(respuesta,'Sin resultados')
        self.assertEqual(self.client.get(self.url('matriculas'),{'desde':'2026-03-01','hasta':'2026-01-01'}).status_code,400)
        self.assertEqual(self.client.get(self.url('matriculas'),{'curso':self.curso.pk,'ciclo':self.segundo.pk}).status_code,400)
        self.assertEqual(self.client.get(self.url('matriculas'),{'ciclo':'9999999'}).status_code,400)

    def test_pagos_no_duplica_detalles_y_excluye_anulados(self):
        self.login('SECRETARIA')
        respuesta=self.client.get(self.url('pagos'),{'desde':'2026-02-10','hasta':'2026-02-10'})
        self.assertEqual(len(respuesta.context['filas']),1)
        self.assertEqual(respuesta.context['totales'][-1][1],'USD 30.00')
        self.assertNotContains(respuesta,'NO-CONTAR-ANULADO')
        respuesta=self.client.get(self.url('pagos'),{'ciclo':self.ciclo.pk})
        self.assertEqual(respuesta.context['filas'][0][-2:],[ 'USD 10.00','USD 30.00'])
        self.assertEqual(respuesta.context['totales'][-1][1],'USD 10.00')
        respuesta=self.client.get(self.url('pagos'),{'ciclo':self.segundo.pk})
        self.assertEqual(respuesta.context['totales'][-1][1],'USD 20.00')

    def test_saldos_y_resumen_separan_ingresos_sin_consolidacion_inventada(self):
        self.login('DIRECTORA')
        respuesta=self.client.get(self.url('pendientes'))
        self.assertEqual(respuesta.context['totales'][-1][1],'USD 55.00')
        self.assertContains(respuesta,'INSOLVENTE')
        respuesta=self.client.get(self.url('resumen'))
        filas=respuesta.context['filas']
        self.assertEqual([f[1] for f in filas],['USD 30.00','USD 55.00','USD 70.00'])
        respuesta=self.client.get(self.url('resumen'),{'ciclo':self.ciclo.pk})
        self.assertEqual([f[1] for f in respuesta.context['filas']],['USD 10.00','USD 25.00','No disponible'])
        Obligacion.objects.filter(pk=self.obligacion.pk).update(estado='ANULADA')
        self.assertEqual(self.client.get(self.url('pendientes')).context['totales'][-1][1],'USD 30.00')

    def test_exportacion_csv_imprimible_y_lectura_sin_cambios(self):
        self.login()
        modelos=(Matricula,InscripcionCurso,Asistencia,Calificacion,Pago,DetallePago,Obligacion,Ingreso)
        antes=[list(m.objects.values()) for m in modelos]
        # Un nombre con prefijo de fórmula debe seguir siendo texto en Excel.
        Estudiante.objects.filter(pk=self.estudiante.pk).update(nombres='=FORMULA_FICTICIA')
        respuesta=self.client.get(self.url('matriculas'),{'estudiante':self.estudiante.pk,'formato':'csv'})
        self.assertEqual(respuesta.status_code,200)
        self.assertIn('text/csv',respuesta['Content-Type'])
        contenido=respuesta.content.decode('utf-8-sig')
        filas=list(csv.reader(io.StringIO(contenido)))
        self.assertTrue(any(any(celda.startswith("'=FORMULA_FICTICIA") for celda in fila) for fila in filas))
        self.assertNotIn('RESERVADO-AJENO',contenido)
        respuesta=self.client.get(self.url('calificaciones'),{'formato':'imprimir'})
        self.assertContains(respuesta,'Imprimir / Guardar PDF')
        self.assertContains(respuesta,'84.00')
        self.assertEqual(self.client.post(self.url('pagos'),{}).status_code,405)
        self.assertEqual(self.client.get(self.url('pagos'),{'formato':'desconocido'}).status_code,400)
        self.assertEqual(antes,[list(m.objects.values()) for m in modelos])
