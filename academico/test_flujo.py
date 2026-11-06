from datetime import date, time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Usuario
from .flujo import (autorizar_extra, cerrar_curso, firma_calendario, guardar_calendario,
                    matricular, propuesta, requisitos_cierre)
from .models import (Asistencia, Calificacion, CicloAcademico, Curso, Estudiante, InscripcionCurso, Maestro,
                     Materia, Matricula, SesionClase)


class FlujoAcademicoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.docente = Usuario.objects.create_user('doc-flujo','doc@example.test','clave',rol='MAESTRO')
        cls.secretaria = Usuario.objects.create_user('sec-flujo','sec@example.test','clave',rol='SECRETARIA')
        cls.directora = Usuario.objects.create_user('dir-flujo','dir@example.test','clave',rol='DIRECTORA')
        cls.maestro = Maestro.objects.create(usuario=cls.docente,nombres='Docente ficticio',apellidos='Prueba',pais='SV',estado='ACTIVO')
        cls.ciclo = CicloAcademico.objects.create(nombre='I',numero_ciclo=1,anio=2026,
            fecha_inicio=date(2026,1,1),fecha_fin=date(2026,12,31),estado='ACTIVO')
        cls.estudiante = Estudiante.objects.create(codigo_estudiante='FLUJO-E1',nombres='Estudiante ficticio',
            apellidos='Prueba',fecha_ingreso=date(2026,1,1),estado='ACTIVO')
        cls.cursos = []
        for i in range(6):
            materia = Materia.objects.create(codigo_materia=f'FLUJO-{i}',nombre=f'Materia {i}',numero_ciclo_formativo=1,estado='ACTIVA')
            cls.cursos.append(Curso.objects.create(materia=materia,maestro=cls.maestro,ciclo=cls.ciclo,
                fecha_inicio=date(2026,1,1),fecha_fin=date(2026,12,31),modalidad='PRESENCIAL',estado='ACTIVO'))

    def matricular(self):
        return matricular(estudiante=self.estudiante,ciclo=self.ciclo,numero_matricula='FLUJO-M1',fecha_matricula=date(2026,1,2))

    def calendario(self):
        return propuesta(date(2026,2,1),'semanal',time(8),90)

    def firma(self):
        curso = Curso.objects.get(pk=self.cursos[0].pk)
        return firma_calendario(curso,list(SesionClase.objects.filter(curso=curso).order_by('numero_clase')))

    def sesion(self,n=1,estado='PROGRAMADA'):
        return SesionClase.objects.create(curso=self.cursos[0],numero_clase=n,fecha=date(2026,2,n),
            hora_inicio=time(8),hora_fin=time(9),estado=estado)

    def test_matricula_seis_inscripciones_e_idempotencia(self):
        matricula, inscripciones, creada = self.matricular()
        self.assertTrue(creada)
        self.assertEqual(len(inscripciones),6)
        otra, inscripciones2, creada = self.matricular()
        self.assertFalse(creada)
        self.assertEqual(otra.pk,matricula.pk)
        self.assertEqual([i.pk for i in inscripciones],[i.pk for i in inscripciones2])
        self.assertEqual(Matricula.objects.count(),1)
        self.assertEqual(InscripcionCurso.objects.count(),6)

    def test_preserva_inscripcion_cerrada_docente_y_datos_existentes(self):
        antes_docente = Maestro.objects.values().get(pk=self.maestro.pk)
        _, inscripciones, _ = self.matricular()
        fila = inscripciones[0]
        fila.estado='REPROBADA_POR_INASISTENCIA';fila.fecha_cierre=date(2026,2,1);fila.motivo_cierre='Cierre previo';fila.save()
        antes = InscripcionCurso.objects.values().get(pk=fila.pk)
        self.matricular()
        self.assertEqual(InscripcionCurso.objects.values().get(pk=fila.pk),antes)
        self.assertEqual(Maestro.objects.values().get(pk=self.maestro.pk),antes_docente)

    def test_configuracion_incompleta_o_cancelada_no_crea_matricula(self):
        Curso.objects.filter(pk=self.cursos[-1].pk).update(estado='CANCELADO')
        with self.assertRaises(ValidationError): self.matricular()
        self.assertFalse(Matricula.objects.exists())
        Curso.objects.filter(pk=self.cursos[-1].pk).update(estado='ACTIVO')
        Materia.objects.create(codigo_materia='EXTRA-FICTICIA',nombre='Extra',numero_ciclo_formativo=1,estado='ACTIVA')
        with self.assertRaises(ValidationError): self.matricular()
        self.assertFalse(Matricula.objects.exists())

    def test_fallo_de_inscripcion_revierte_matricula_y_lote(self):
        guardar = InscripcionCurso.save
        contador = [0]
        def fallo(obj,*args,**kwargs):
            contador[0]+=1
            if contador[0] == 3: raise ValidationError('Fallo simulado')
            return guardar(obj,*args,**kwargs)
        with patch.object(InscripcionCurso,'save',fallo), self.assertRaises(ValidationError): self.matricular()
        self.assertFalse(Matricula.objects.exists())
        self.assertFalse(InscripcionCurso.objects.exists())

    def test_matricula_existente_con_datos_distintos_no_se_sobrescribe(self):
        self.matricular()
        with self.assertRaises(ValidationError):
            matricular(estudiante=self.estudiante,ciclo=self.ciclo,numero_matricula='DISTINTA',fecha_matricula=date(2026,1,2))
        self.assertEqual(Matricula.objects.get().numero_matricula,'FLUJO-M1')

    def test_secretaria_web_y_docente_sin_permiso(self):
        url=reverse('matricula_secretaria')
        self.client.force_login(self.docente)
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.secretaria)
        datos={'estudiante':self.estudiante.pk,'ciclo':self.ciclo.pk,'numero_matricula':'FLUJO-M1','fecha_matricula':'2026-01-02'}
        respuesta=self.client.post(url,datos)
        self.assertContains(respuesta,'Matrícula registrada con sus seis materias')
        self.assertEqual(InscripcionCurso.objects.count(),6)
        self.client.post(url,datos)
        self.assertEqual(InscripcionCurso.objects.count(),6)

    def test_admin_crea_matricula_activa_con_seis_inscripciones(self):
        self.secretaria.is_staff=True;self.secretaria.is_superuser=True;self.secretaria.save()
        self.client.force_login(self.secretaria)
        respuesta=self.client.post(reverse('admin:academico_matricula_add'),{
            'estudiante':self.estudiante.pk,'ciclo':self.ciclo.pk,'numero_matricula':'ADMIN-M1',
            'fecha_matricula':'2026-01-02','estado':'ACTIVA','_save':'Guardar'})
        self.assertEqual(respuesta.status_code,302)
        self.assertEqual(InscripcionCurso.objects.count(),6)

    def test_frecuencias_explicitas_y_personalizada(self):
        for frecuencia,dias,intervalo in [('semanal',7,None),('quincenal',14,None),('personalizada',3,3)]:
            filas=propuesta(date(2026,2,1),frecuencia,time(8),90,intervalo)
            self.assertEqual(len(filas),6)
            self.assertEqual((filas[1]['fecha']-filas[0]['fecha']).days,dias)
            self.assertEqual(filas[0]['hora_fin'],time(9,30))
        for frecuencia,intervalo in [('',None),('personalizada',None)]:
            with self.assertRaises(ValidationError): propuesta(date(2026,2,1),frecuencia,time(8),90,intervalo)
        with self.assertRaises(ValidationError): propuesta(date(2026,2,1),'semanal',time(23),120)

    def test_calendario_editable_seis_ordinarias_y_no_extraordinarias(self):
        filas=self.calendario();filas[2]['fecha']=date(2026,2,20)
        self.assertEqual(guardar_calendario(self.cursos[0].pk,self.docente,filas,self.firma()),6)
        self.assertEqual(set(SesionClase.objects.values_list('numero_clase',flat=True)),set(range(1,7)))
        self.assertFalse(SesionClase.objects.filter(es_extraordinaria=True).exists())
        self.assertEqual(SesionClase.objects.get(numero_clase=3).fecha,date(2026,2,20))

    def test_preserva_sesion_existente_y_rechaza_sobrescritura(self):
        sesion=self.sesion();antes=SesionClase.objects.values().get(pk=sesion.pk)
        filas=self.calendario()
        # La clase existente tiene otros horarios: el servicio no permite cambiarlos.
        with self.assertRaises(ValidationError): guardar_calendario(self.cursos[0].pk,self.docente,filas,self.firma())
        filas[0]={'numero_clase':1,'fecha':sesion.fecha,'hora_inicio':sesion.hora_inicio,'hora_fin':sesion.hora_fin}
        self.assertEqual(guardar_calendario(self.cursos[0].pk,self.docente,filas,self.firma()),5)
        self.assertEqual(SesionClase.objects.values().get(pk=sesion.pk),antes)

    def test_revision_obsoleta_y_calendario_invalido_no_guardan_parcialmente(self):
        revision=self.firma();self.sesion()
        with self.assertRaises(ValidationError): guardar_calendario(self.cursos[0].pk,self.docente,self.calendario(),revision)
        self.assertEqual(SesionClase.objects.count(),1)
        filas=self.calendario();filas[-1]['fecha']=date(2027,1,1)
        with self.assertRaises(ValidationError): guardar_calendario(self.cursos[1].pk,self.docente,filas,
            firma_calendario(self.cursos[1],[]))
        self.assertEqual(SesionClase.objects.count(),1)

    def test_docente_no_programa_curso_ajeno(self):
        otra=Usuario.objects.create_user('otro-flujo','otro@example.test','clave',rol='MAESTRO')
        self.client.force_login(otra)
        self.assertEqual(self.client.get(reverse('programar_sesiones',args=[self.cursos[0].pk])).status_code,404)
        with self.assertRaises(ValidationError): guardar_calendario(self.cursos[0].pk,otra,self.calendario(),self.firma())

    def test_web_propone_y_confirma_calendario(self):
        self.client.force_login(self.docente)
        url=reverse('programar_sesiones',args=[self.cursos[0].pk])
        respuesta=self.client.post(url,{'accion':'proponer','fecha_inicial':'2026-02-01',
            'frecuencia':'semanal','hora_inicio':'08:00','duracion_minutos':'90'})
        self.assertEqual(len(respuesta.context['filas']),6)
        self.assertFalse(SesionClase.objects.exists())
        datos={'accion':'guardar','revision':respuesta.context['revision']}
        for fila in respuesta.context['filas']:
            for nombre in ('fecha','hora_inicio','hora_fin'):
                datos[fila.add_prefix(nombre)]=str(fila.initial[nombre])
        respuesta=self.client.post(url,datos,follow=True)
        self.assertContains(respuesta,'6 sesiones ordinarias creadas')
        self.assertEqual(SesionClase.objects.count(),6)

    def test_extraordinaria_autoriza_solo_directora_y_no_id_elegido(self):
        url=reverse('autorizar_clase_extraordinaria')
        self.client.force_login(self.docente)
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.directora)
        respuesta=self.client.get(url)
        self.assertNotContains(respuesta,'name="usuario_autoriza"')
        self.assertNotContains(respuesta,'name="fecha_autorizacion"')
        datos={'curso':self.cursos[0].pk,'numero_clase':7,'fecha':'2026-04-01','hora_inicio':'08:00',
            'hora_fin':'09:00','motivo_extension':'Motivo ficticio','estado':'PROGRAMADA',
            'usuario_autoriza':self.docente.pk,'fecha_autorizacion':'2000-01-01T00:00'}
        respuesta=self.client.post(url,datos)
        self.assertEqual(respuesta.status_code,302)
        sesion=SesionClase.objects.get(numero_clase=7)
        self.assertEqual(sesion.usuario_autoriza_id,self.directora.pk)
        self.assertNotEqual(sesion.fecha_autorizacion.year,2000)
        self.client.post(url,datos)
        self.assertEqual(SesionClase.objects.count(),1)

    def test_servicio_extraordinario_rechaza_docente(self):
        sesion=SesionClase(curso=self.cursos[0],numero_clase=7,fecha=date(2026,4,1),
            hora_inicio=time(8),hora_fin=time(9),estado='PROGRAMADA',motivo_extension='Ficticio')
        with self.assertRaises(ValidationError): autorizar_extra(sesion,self.docente)
        self.assertFalse(SesionClase.objects.exists())

    def test_cierre_minimo_cinco_sin_pendientes_preserva_inscripciones(self):
        self.matricular()
        antes=list(InscripcionCurso.objects.values())
        for n in range(1,6): self.sesion(n,'IMPARTIDA')
        self.sesion(6,'PROGRAMADA')
        self.assertTrue(requisitos_cierre(self.cursos[0]))
        with self.assertRaises(ValidationError): cerrar_curso(self.cursos[0].pk,self.docente,self.firma())
        SesionClase.objects.filter(numero_clase=6).update(estado='CANCELADA')
        self.assertFalse(requisitos_cierre(self.cursos[0]))
        cerrar_curso(self.cursos[0].pk,self.docente,self.firma())
        self.cursos[0].refresh_from_db();self.assertEqual(self.cursos[0].estado,'FINALIZADO')
        self.assertEqual(list(InscripcionCurso.objects.values()),antes)
        self.assertEqual(SesionClase.objects.get(numero_clase=6).estado,'CANCELADA')

    def test_cierre_guiado_muestra_requisitos_sin_modificar(self):
        self.client.force_login(self.docente)
        respuesta=self.client.get(reverse('cierre_curso',args=[self.cursos[0].pk]))
        self.assertContains(respuesta,'al menos 5 clases impartidas')
        self.cursos[0].refresh_from_db();self.assertEqual(self.cursos[0].estado,'ACTIVO')

    def test_acceso_directo_desde_dashboard(self):
        self.client.force_login(self.docente)
        self.assertContains(self.client.get(reverse('dashboard')),reverse('mis_cursos'))
        self.assertContains(self.client.get(reverse('mis_cursos')),reverse('registrar_asistencia'))


    def test_reintento_preserva_notas_y_asistencias(self):
        _, inscripciones, _ = self.matricular()
        sesion=self.sesion()
        Asistencia.objects.create(inscripcion=inscripciones[0],sesion=sesion,estado_asistencia='PRESENTE')
        nota=Calificacion(inscripcion=inscripciones[0],**dict(zip(Calificacion.COMPONENTES,[40,20,20,20,0,75,75,75,75])))
        nota.save()
        antes=(list(Calificacion.objects.values()),list(Asistencia.objects.values()),list(InscripcionCurso.objects.values()))
        self.matricular()
        despues=(list(Calificacion.objects.values()),list(Asistencia.objects.values()),list(InscripcionCurso.objects.values()))
        self.assertEqual(antes,despues)

    def test_fallo_al_guardar_calendario_revierte_las_sesiones_nuevas(self):
        original=SesionClase.save
        def guardar(sesion,*args,**kwargs):
            if sesion.numero_clase==3: raise ValidationError('Fallo simulado')
            return original(sesion,*args,**kwargs)
        with patch.object(SesionClase,'save',guardar),self.assertRaises(ValidationError):
            guardar_calendario(self.cursos[0].pk,self.docente,self.calendario(),self.firma())
        self.assertFalse(SesionClase.objects.exists())

    def test_no_asume_frecuencia_en_web(self):
        self.client.force_login(self.docente)
        respuesta=self.client.post(reverse('programar_sesiones',args=[self.cursos[0].pk]),{
            'accion':'proponer','fecha_inicial':'2026-02-01','hora_inicio':'08:00','duracion_minutos':'90'})
        self.assertIn('frecuencia',respuesta.context['configuracion'].errors)
        self.assertFalse(SesionClase.objects.exists())

    def test_curso_cancelado_no_programa_ni_reabre(self):
        Curso.objects.filter(pk=self.cursos[0].pk).update(estado='CANCELADO')
        self.client.force_login(self.docente)
        respuesta=self.client.get(reverse('programar_sesiones',args=[self.cursos[0].pk]))
        self.assertContains(respuesta,'calendario solo para consulta')
        self.assertNotContains(respuesta,'Generar propuesta editable')
        with self.assertRaises(ValidationError): cerrar_curso(self.cursos[0].pk,self.docente,self.firma())
        self.assertEqual(Curso.objects.get(pk=self.cursos[0].pk).estado,'CANCELADO')
