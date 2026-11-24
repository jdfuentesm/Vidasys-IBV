"""F8.4: contratos por lote, elegibilidad canónica y permisos; SQLite aislado."""
import re
from decimal import Decimal
from unittest.mock import patch
from html.parser import HTMLParser
from django.db import DatabaseError
from django.test import TestCase, Client
from django.urls import reverse
from . import tests as fixture
from . import test_asistencia as asistencia_fixture
from . import test_correcciones as correccion_fixture
from .models import Calificacion, Curso, Asistencia, InscripcionCurso


class Controles(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.nombres=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if d.get('id'):self.ids.append(d['id'])
        if tag in ('input','select','textarea') and d.get('name'):self.nombres.append(d['name'])


class LibroPresentacionF84Tests(TestCase):
    @classmethod
    def setUpTestData(cls):fixture.CalificacionesTests.setUpTestData.__func__(cls)
    def setUp(self):self.client.force_login(self.docente);self.url=reverse('registrar_calificacion')
    datos=fixture.CalificacionesTests.datos
    libro_datos=fixture.CalificacionesTests.libro_datos
    agregar_inscripcion=fixture.CalificacionesTests.agregar_inscripcion

    def test_campos_unicos_y_componentes_completos(self):
        self.agregar_inscripcion();r=self.client.get(self.url,{'curso':self.cursos[0].pk})
        parser=Controles();parser.feed(r.content.decode())
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        for fila in r.context['filas']:
            for field in fila['form']:
                self.assertEqual(parser.nombres.count(field.html_name),1)
        self.assertEqual(parser.nombres.count('inscripciones'),2)
        self.assertContains(r,'Apreciación y extras');self.assertContains(r,'Exámenes')
        self.assertContains(r,'data-componentes',count=2)

    def test_guardado_por_lote_preserva_formula_y_estado_provisional(self):
        self.agregar_inscripcion();r=self.client.post(self.url,self.libro_datos(),follow=True)
        self.assertContains(r,'Libro guardado correctamente: 2')
        self.assertEqual(Calificacion.objects.count(),2)
        self.assertEqual(set(Calificacion.objects.values_list('nota_final',flat=True)),{Decimal('80')})
        self.assertTrue(all(i.estado=='CURSANDO' for i in InscripcionCurso.objects.filter(curso=self.cursos[0])))

    def test_error_en_una_fila_no_guarda_ninguna_y_conserva_valores(self):
        segunda=self.agregar_inscripcion();datos=self.libro_datos()
        datos[f'nota-{segunda.pk}-tarea_1']='101'
        r=self.client.post(self.url,datos)
        self.assertFalse(Calificacion.objects.exists())
        self.assertContains(r,'data-error-docente')
        self.assertContains(r,'value="101"')
        self.assertContains(r,'data-con-errores')
        self.assertContains(r,'value="75"')

    def test_calcular_usa_servidor_sin_guardar(self):
        r=self.client.post(self.url,self.libro_datos()|{'accion':'calcular'})
        self.assertEqual(Decimal(r.json()['filas'][0]['nota']),Decimal('80'))
        self.assertFalse(Calificacion.objects.exists())

    def test_extras_opcionales_y_limites_originales(self):
        self.client.post(self.url,self.libro_datos(puntos_extras=''))
        self.assertEqual(Calificacion.objects.get().puntos_extras,0)
        for cambios in ({'tarea_1':'100.01'},{'nota_asistencia':'40.01'},{'puntos_extras':'10.01'},{'examen_1':'-1'}):
            antes=list(Calificacion.objects.values())
            r=self.client.post(self.url,self.libro_datos(**cambios))
            self.assertContains(r,'data-error-docente')
            self.assertEqual(list(Calificacion.objects.values()),antes)

    def test_identificadores_ajenos_y_duplicados_rechazados(self):
        self.assertEqual(self.client.get(self.url,{'curso':self.cursos[1].pk}).status_code,404)
        datos=self.libro_datos();datos['inscripciones']*=2
        self.assertEqual(self.client.post(self.url,datos).status_code,403)
        self.assertFalse(Calificacion.objects.exists())

    def test_nota_final_manipulada_no_sustituye_formula(self):
        self.client.post(self.url,self.libro_datos()|{'nota_final':'100','estado':'APROBADA'})
        self.assertEqual(Calificacion.objects.get().nota_final,Decimal('80'))
        self.assertEqual(InscripcionCurso.objects.get(pk=self.inscripciones[0].pk).estado,'CURSANDO')

    def test_curso_cancelado_no_invita_a_editar(self):
        Curso.objects.filter(pk=self.cursos[0].pk).update(estado='CANCELADO')
        r=self.client.get(self.url,{'curso':self.cursos[0].pk})
        self.assertNotContains(r,'Guardar calificaciones provisionales')
        self.assertNotContains(r,'Escriba en las casillas')
        self.assertNotContains(r,'Revisar corrección excepcional')
        self.assertTrue(all(f.disabled for f in r.context['filas'][0]['form'].fields.values()))
        self.assertEqual(self.client.post(self.url,self.libro_datos()).status_code,403)

    def test_inicio_solo_cursos_propios(self):
        r=self.client.get(reverse('dashboard'))
        self.assertEqual([x['curso'].pk for x in r.context['cursos_docente']],[self.cursos[0].pk])
        self.assertContains(r,self.cursos[0].materia.nombre)
        self.assertNotContains(r,self.cursos[1].materia.nombre)
        self.assertLessEqual(r.content.decode().count('acceso-tarjeta ui-tarea'),3)

    def test_inicio_sin_fuente_muestra_aviso(self):
        with patch('academico.presentacion_docente.resumenes_propios',side_effect=DatabaseError):
            r=self.client.get(reverse('dashboard'))
        self.assertContains(r,'No se pudieron consultar sus cursos')
        self.assertNotIn('cursos_docente',r.context)

    def test_selector_ofrece_nombres_completos_fuera_del_select(self):
        r=self.client.get(self.url)
        self.assertContains(r,'Ver nombres completos de mis cursos')
        self.assertContains(r,self.cursos[0].materia.nombre)
        self.assertNotContains(r,self.cursos[1].materia.nombre)

    def test_reportes_propios_conservan_csv_impresion_y_retorno(self):
        url=reverse('reportes_consultar',args=['calificaciones'])
        r=self.client.get(url,{'curso':self.cursos[0].pk})
        self.assertContains(r,'Volver al libro')
        self.assertEqual(self.client.get(url,{'curso':self.cursos[0].pk,'formato':'csv'}).status_code,200)
        self.assertEqual(self.client.get(url,{'curso':self.cursos[0].pk,'formato':'imprimir'}).status_code,200)
        self.assertEqual(self.client.get(url,{'curso':self.cursos[1].pk}).status_code,400)

    def test_csrf_y_otros_roles_sin_acceso(self):
        c=Client(enforce_csrf_checks=True);c.force_login(self.docente)
        self.assertEqual(c.post(self.url,self.libro_datos()).status_code,403)
        self.client.force_login(self.estudiante_usuario)
        self.assertEqual(self.client.get(self.url).status_code,403)


class AsistenciaPresentacionF84Tests(TestCase):
    @classmethod
    def setUpTestData(cls):asistencia_fixture.AsistenciaDocenteTests.setUpTestData.__func__(cls)
    def setUp(self):self.client.force_login(self.docente);self.url=reverse('registrar_asistencia')
    datos=asistencia_fixture.AsistenciaDocenteTests.datos

    def test_guardado_y_modificacion_originales(self):
        self.client.post(self.url,self.datos(),follow=True)
        self.assertEqual(Asistencia.objects.count(),2)
        self.client.post(self.url,self.datos(estado='AUSENTE_JUSTIFICADA'),follow=True)
        self.assertEqual(Asistencia.objects.count(),2)
        self.assertTrue(all(a.estado_asistencia=='AUSENTE_JUSTIFICADA' for a in Asistencia.objects.all()))

    def test_curso_finalizado_no_muestra_guardar(self):
        self.client.post(self.url,self.datos())
        Curso.objects.filter(pk=self.curso.pk).update(estado='FINALIZADO')
        r=self.client.get(self.url,{'curso':self.curso.pk,'sesion':self.sesion.pk})
        self.assertFalse(r.context['edicion_asistencia'])
        self.assertNotContains(r,'>Guardar asistencia</button>')
        self.assertContains(r,'solo para consulta')
        self.assertTrue(all(f['form'].fields['estado_asistencia'].disabled for f in r.context['filas']))
        self.assertEqual(self.client.post(self.url,{'curso':self.curso.pk,'sesion':self.sesion.pk}).status_code,403)

    def test_sesion_suspendida_sin_accion_de_guardado(self):
        self.sesion.estado='SUSPENDIDA';self.sesion.save()
        r=self.client.get(self.url,{'curso':self.curso.pk,'sesion':self.sesion.pk})
        self.assertFalse(r.context['edicion_asistencia'])
        self.assertNotContains(r,'>Guardar asistencia</button>')

    def test_asistencia_campos_unicos_y_error_preservado(self):
        datos=self.datos();datos[f'asistencia-{self.inscripcion.pk}-estado_asistencia']=''
        datos[f'asistencia-{self.inscripcion.pk}-observaciones']='Conservar esta observación'
        r=self.client.post(self.url,datos)
        self.assertContains(r,'Conservar esta observación')
        self.assertContains(r,'data-error-docente')
        self.assertFalse(Asistencia.objects.exists())
        p=Controles();p.feed(r.content.decode());self.assertEqual(len(p.ids),len(set(p.ids)))
        for fila in r.context['filas']:
            for field in fila['form']:self.assertEqual(p.nombres.count(field.html_name),1)


class CorreccionesPresentacionF84Tests(TestCase):
    @classmethod
    def setUpTestData(cls):correccion_fixture.CorreccionesTests.setUpTestData.__func__(cls)
    def setUp(self):correccion_fixture.CorreccionesTests.setUp(self)
    recargar=correccion_fixture.CorreccionesTests.recargar
    componentes=correccion_fixture.CorreccionesTests.componentes
    solicitar=correccion_fixture.CorreccionesTests.solicitar

    def libro(self):return self.client.get(reverse('registrar_calificacion'),{'curso':self.curso.pk})

    def test_correccion_elegible_usa_validador_original(self):
        from .correcciones import validar_destino
        with patch('academico.presentacion_docente.validar_destino',wraps=validar_destino) as validar:
            r=self.libro()
        self.assertEqual(validar.call_count,1)
        self.assertTrue(r.context['filas'][0]['correccion_disponible'])
        self.assertContains(r,reverse('solicitar_correccion',args=[self.inscripcion.pk]))
        self.assertNotContains(r,'Escriba en las casillas')

    def test_inasistencia_no_muestra_enlace_ni_cambia_nota(self):
        InscripcionCurso.objects.filter(pk=self.inscripcion.pk).update(estado='REPROBADA_POR_INASISTENCIA')
        antes=list(Calificacion.objects.values())
        r=self.libro()
        self.assertFalse(r.context['filas'][0]['correccion_disponible'])
        self.assertNotContains(r,reverse('solicitar_correccion',args=[self.inscripcion.pk]))
        self.assertContains(r,'dos ausencias injustificadas')
        self.assertEqual(list(Calificacion.objects.values()),antes)

    def test_pendiente_propia_enlaza_historial_no_nueva_propuesta(self):
        s=self.solicitar();r=self.libro()
        self.assertNotContains(r,reverse('solicitar_correccion',args=[self.inscripcion.pk]))
        self.assertContains(r,reverse('solicitud_academica',args=[s.pk]))
        self.assertContains(r,'Consultar solicitud pendiente')

    def test_datos_incoherentes_o_nota_faltante_no_habilitan(self):
        Calificacion.objects.filter(pk=self.nota.pk).update(nota_final=Decimal('99'))
        r=self.libro();self.assertFalse(r.context['filas'][0]['correccion_disponible'])
        Calificacion.objects.filter(pk=self.nota.pk).delete()
        r=self.libro();self.assertFalse(r.context['filas'][0]['correccion_disponible'])
        self.assertContains(r,'No existe una calificación definitiva')

    def test_fallo_fuente_no_habilita_correccion(self):
        with patch('academico.presentacion_docente.validar_destino',side_effect=DatabaseError):r=self.libro()
        self.assertFalse(r.context['filas'][0]['correccion_disponible'])
        self.assertContains(r,'No se pudo comprobar la disponibilidad')

    def test_dos_injustificadas_con_estado_inconsistente_siguen_bloqueando(self):
        ids=list(Asistencia.objects.filter(inscripcion=self.inscripcion).order_by('pk').values_list('pk',flat=True)[:2])
        Asistencia.objects.filter(pk__in=ids).update(estado_asistencia='AUSENTE_INJUSTIFICADA')
        r=self.libro()
        self.assertFalse(r.context['filas'][0]['correccion_disponible'])
        self.assertNotContains(r,reverse('solicitar_correccion',args=[self.inscripcion.pk]))
        self.assertEqual(InscripcionCurso.objects.get(pk=self.inscripcion.pk).estado,'APROBADA')
