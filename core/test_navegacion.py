"""F8.1: navegación, semántica y enlaces reales por rol; SQLite aislado."""
from html.parser import HTMLParser
from types import SimpleNamespace
from django.test import TestCase
from django.urls import reverse
from django.template.loader import render_to_string
from .templatetags.navegacion import construir_menu
from . import test_frontend as fixtures


class Enlaces(HTMLParser):
    def __init__(self):super().__init__();self.enlaces=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.enlaces.append(dict(attrs))


class NavegacionF81Tests(TestCase):
    @classmethod
    def setUpTestData(cls):fixtures.FrontendInstitucionalTests.setUpTestData.__func__(cls)

    def pagina(self,rol,ruta='dashboard',**kwargs):
        self.client.force_login(self.usuarios[rol]);return self.client.get(reverse(ruta,kwargs=kwargs))

    def test_enlaces_del_menu_responden_para_cada_rol(self):
        for rol,u in self.usuarios.items():
            self.client.force_login(u);menu=construir_menu(u)
            items=menu['principales']+[x for g in menu['grupos'] for x in g['enlaces']]
            for item in items:
                with self.subTest(rol=rol,ruta=item['ruta']):
                    # El rol estudiante conserva su entrada; el control financiero existente
                    # bloquea el expediente académico de esta fixture insolvente.
                    esperado=403 if rol=='ESTUDIANTE' and item['ruta']=='portal_academico' else 200
                    self.assertEqual(self.client.get(item['url'],follow=True).status_code,esperado)

    def test_inicio_muestra_tres_prioridades_como_maximo(self):
        for rol in ('DIRECTORA','SECRETARIA','ADMINISTRADOR','MAESTRO'):
            r=self.pagina(rol);self.assertEqual(r.status_code,200)
            self.assertLessEqual(r.content.decode().count('acceso-tarjeta ui-tarea'),3)
            self.assertContains(r,'Tareas principales')
            self.assertContains(r,'Otras tareas disponibles')

    def test_tareas_secundarias_no_se_pierden(self):
        for rol,esperados in {'DIRECTORA':['finanzas_panel','matricula_secretaria','reportes','autorizar_clase_extraordinaria'],
            'ADMINISTRADOR':['estudiantes','matricula_secretaria','reportes'],
            'MAESTRO':['solicitudes_academicas','reportes']}.items():
            menu=construir_menu(self.usuarios[rol]);self.assertEqual([x['ruta'] for x in menu['otras']],esperados)

    def test_maestro_encuentra_sus_solicitudes_sin_accesos_financieros(self):
        menu=construir_menu(self.usuarios['MAESTRO'])
        self.assertIn('solicitudes_academicas',[i['ruta'] for i in menu['principales']])
        self.assertEqual(menu['grupos'],[])

    def test_un_solo_enlace_activo_en_menu_financiero(self):
        for nombre in ('finanzas_panel','caja_detalle','operaciones_egreso','becas_detalle','convenios_cobro','aportes_solicitud','anulaciones_detalle','finanzas_reporte'):
            menu=construir_menu(self.usuarios['DIRECTORA'],nombre)
            enlaces=menu['principales']+[i for g in menu['grupos'] for i in g['enlaces']]
            self.assertEqual(sum(i['activo'] for i in enlaces),1,nombre)
            self.assertTrue(menu['seccion']['activo'])

    def test_matricula_no_activa_estudiantes_por_coincidencia_parcial(self):
        menu=construir_menu(self.usuarios['SECRETARIA'],'estudiante_matricular')
        self.assertEqual([i['ruta'] for i in menu['principales'] if i['activo']],['matricula_secretaria'])

    def test_reportes_financieros_se_distinguen_de_cobros(self):
        menu=construir_menu(self.usuarios['DIRECTORA'],'finanzas_reporte')
        self.assertEqual(menu['seccion']['id'],'reportes')
        for g in menu['grupos']:
            if g['id']=='finanzas':self.assertFalse(g['activo'])

    def test_grupo_actual_abierto_y_otros_plegados(self):
        r=self.pagina('DIRECTORA','finanzas_panel');html=r.content.decode()
        self.assertIn('class="menu-grupo" open',html)
        self.assertContains(r,'Navegación de Finanzas');self.assertContains(r,'Cambiar de sección')
        self.assertContains(r,'aria-current="page"')

    def test_semantica_foco_y_menu_con_controles_explicitos(self):
        r=self.pagina('ADMINISTRADOR');html=r.content.decode()
        self.assertContains(r,'aria-label="Menú principal"')
        self.assertContains(r,'aria-controls="menu-app" aria-expanded="false"')
        self.assertContains(r,'<main id="contenido" class="app-main" tabindex="-1">')
        self.assertContains(r,'href="#contenido"')
        self.assertContains(r,'css/sistema_visual.css')
        self.assertEqual(html.count('<main '),1);self.assertEqual(html.count('<h1>'),1)

    def test_estudiante_y_pastor_no_reciben_finanzas_internas(self):
        for rol in ('ESTUDIANTE','PASTOR_PRINCIPAL'):
            menu=construir_menu(self.usuarios[rol]);self.assertEqual(menu['grupos'],[])
            self.assertFalse(menu['tareas']);self.assertFalse(menu['otras'])

        menu=construir_menu(self.usuarios['ESTUDIANTE'],'convenios_portal')
        self.assertEqual([i['ruta'] for i in menu['principales'] if i['activo']],['portal_cuenta'])

    def test_cuenta_inactiva_no_recibe_modulos(self):
        u=SimpleNamespace(is_authenticated=True,is_active=False,rol='DIRECTORA')
        menu=construir_menu(u)
        self.assertEqual([x['ruta'] for x in menu['principales']],['dashboard'])
        self.assertFalse(menu['grupos'])

    def test_menu_es_presentacion_sin_consultas(self):
        with self.assertNumQueries(0):construir_menu(self.usuarios['DIRECTORA'],'finanzas_reporte')

    def test_componentes_escapan_contenido_y_distinguen_error(self):
        html=render_to_string('core/componentes/aviso.html',{'texto':'<script>alert(1)</script>','tipo':'error'})
        self.assertIn('role="alert"',html);self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)
        html=render_to_string('core/componentes/aviso.html',{'texto':'Guardado','tipo':'success'})
        self.assertIn('role="status"',html)

    def test_ayuda_accesible_sin_javascript_y_abierta_al_imprimir(self):
        html=render_to_string('core/componentes/ayuda.html',{'titulo':'Criterios','texto':'Detalle verificable'})
        self.assertIn('<summary>Criterios</summary>',html);self.assertIn('Detalle verificable',html)
        self.assertNotIn(' open',html)
        self.assertIn(' open',render_to_string('core/componentes/ayuda.html',{'texto':'Detalle','imprimir':True}))

    def test_no_cambian_formularios_ni_campos_en_ayuda(self):
        r=self.pagina('DIRECTORA','finanzas_reporte',tipo='resultados')
        self.assertContains(r,'Elegir reporte financiero')
        self.assertContains(r,'Criterios y cálculo del reporte')
        for campo in ('desde','hasta','ciclo','estudiante','categoria','metodo','operador','estado','origen'):
            self.assertContains(r,f'name="{campo}"',count=1)

    def test_secretaria_no_ve_centro_consolidado_ni_usuarios(self):
        r=self.pagina('SECRETARIA');html=r.content.decode()
        self.assertNotIn('href="'+reverse('finanzas_centro')+'"',html)
        self.assertNotIn('href="'+reverse('usuarios')+'"',html)
        self.assertNotIn('href="'+reverse('autorizar_clase_extraordinaria')+'"',html)
