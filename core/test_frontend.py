"""Integración de navegación por rol; SQLite aislado, sin estadísticas ficticias."""
import re
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from academico import test_flujo as fixtures
from academico.flujo import matricular
from academico.models import SesionClase
from core.models import Usuario


class Controles(HTMLParser):
    def __init__(self):
        super().__init__()
        self.campos = []

    def handle_starttag(self, tag, attrs):
        datos = dict(attrs)
        if tag in ('input', 'select', 'textarea'):
            self.campos.append((datos.get('name'), datos.get('id')))


class FrontendInstitucionalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.FlujoAcademicoTests.setUpTestData()
        base = fixtures.FlujoAcademicoTests
        cls.usuarios = {'MAESTRO': base.docente, 'SECRETARIA': base.secretaria, 'DIRECTORA': base.directora}
        for rol in ('ADMINISTRADOR','ESTUDIANTE','PASTOR_PRINCIPAL'):
            cls.usuarios[rol] = Usuario.objects.create_user(rol.lower()+'-ui',rol.lower()+'@example.test','clave',rol=rol)
        cls.curso = base.cursos[0]
        matricular(estudiante=base.estudiante,ciclo=base.ciclo,numero_matricula='UI-M1',fecha_matricula=base.ciclo.fecha_inicio)
        from datetime import date, time
        cls.sesion = SesionClase.objects.create(curso=cls.curso,numero_clase=1,fecha=date(2026,2,1),
            hora_inicio=time(8),hora_fin=time(9),estado='PROGRAMADA')

    def sidebar(self,respuesta):
        html=respuesta.content.decode()
        return html.split('<aside id="menu-app"',1)[1].split('</aside>',1)[0]

    def test_menu_exacto_por_rol_sin_enlaces_ficticios(self):
        esperados={
            'MAESTRO':['dashboard','mis_cursos'],
            'SECRETARIA':['dashboard','matricula_secretaria'],
            'DIRECTORA':['dashboard','matricula_secretaria','autorizar_clase_extraordinaria'],
            'ADMINISTRADOR':['dashboard','matricula_secretaria'],
            'ESTUDIANTE':['dashboard'], 'PASTOR_PRINCIPAL':['dashboard'],
        }
        for rol,usuario in self.usuarios.items():
            with self.subTest(rol=rol):
                self.client.force_login(usuario)
                respuesta=self.client.get(reverse('dashboard'))
                self.assertEqual(respuesta.status_code,200)
                self.assertEqual(re.findall(r'href="([^"]+)"',self.sidebar(respuesta)),[reverse(n) for n in esperados[rol]])
                self.assertNotContains(respuesta,'href="#"')
                self.assertContains(respuesta,reverse('logout'))
                self.assertContains(respuesta,usuario.get_rol_display())
                self.assertContains(respuesta,'src="/static/img/logo.png"')
                self.assertEqual(respuesta.content.decode().count('<h1>'),1)

    def test_dashboard_sin_metricas_demostrativas(self):
        self.client.force_login(self.usuarios['DIRECTORA'])
        respuesta=self.client.get(reverse('dashboard'))
        for texto in ('Dashboard en construcción','>284<','>12<','92%','+12%','Teologia Sistematica','08:00 PM'):
            self.assertNotContains(respuesta,texto)
        for modulo in ('Finanzas','Reportes','Usuarios','Estudiantes'):
            self.assertNotIn(modulo,self.sidebar(respuesta))

    def test_roles_sin_modulo_tienen_estado_vacio_honesto(self):
        for rol in ('ESTUDIANTE','PASTOR_PRINCIPAL'):
            self.client.force_login(self.usuarios[rol])
            self.assertContains(self.client.get(reverse('dashboard')),'Todavía no hay módulos de consulta habilitados para su rol')

    def test_admin_no_recibe_permisos_docentes(self):
        for rol in ('ADMINISTRADOR','DIRECTORA','SECRETARIA','ESTUDIANTE','PASTOR_PRINCIPAL'):
            self.client.force_login(self.usuarios[rol])
            for nombre,args in [('mis_cursos',[]),('registrar_asistencia',[]),('registrar_calificacion',[]),
                                ('programar_sesiones',[self.curso.pk]),('cierre_curso',[self.curso.pk])]:
                with self.subTest(rol=rol,ruta=nombre):
                    self.assertEqual(self.client.get(reverse(nombre,args=args)).status_code,403)

    def test_autorizacion_de_extraordinarias_conservada(self):
        for rol,usuario in self.usuarios.items():
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('autorizar_clase_extraordinaria')).status_code,200 if rol=='DIRECTORA' else 403)

    def test_estructura_compartida_y_contexto_en_todas_las_pantallas_docentes(self):
        self.client.force_login(self.usuarios['MAESTRO'])
        rutas=[reverse('mis_cursos'),reverse('registrar_asistencia')+f'?curso={self.curso.pk}&sesion={self.sesion.pk}',
               reverse('registrar_calificacion')+f'?curso={self.curso.pk}',
               reverse('programar_sesiones',args=[self.curso.pk]),reverse('cierre_curso',args=[self.curso.pk])]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta=self.client.get(ruta)
                self.assertEqual(respuesta.status_code,200)
                self.assertContains(respuesta,'id="menu-app"')
                self.assertContains(respuesta,'aria-controls="menu-app"')
                self.assertContains(respuesta,reverse('logout'))
                self.assertContains(respuesta,'aria-current="page"')
                self.assertNotContains(respuesta,'href="#"')
                self.assertEqual(respuesta.content.decode().count('<main '),1)
                self.assertContains(respuesta,'css/institucional.css')
                self.assertNotContains(respuesta,'css/dashboard.css')
                if ruta!=reverse('mis_cursos'):
                    self.assertContains(respuesta,f'{reverse("registrar_calificacion")}?curso={self.curso.pk}')
                    self.assertContains(respuesta,reverse('programar_sesiones',args=[self.curso.pk]))

    def test_campos_del_libro_y_asistencia_no_cambian(self):
        self.client.force_login(self.usuarios['MAESTRO'])
        rutas=[reverse('registrar_calificacion')+f'?curso={self.curso.pk}',
               reverse('registrar_asistencia')+f'?curso={self.curso.pk}&sesion={self.sesion.pk}']
        for ruta in rutas:
            respuesta=self.client.get(ruta)
            controles=Controles();controles.feed(respuesta.content.decode())
            for fila in respuesta.context['filas']:
                for campo in fila['form']:
                    self.assertEqual(controles.campos.count((campo.html_name,campo.auto_id)),1)
            self.assertTrue(any(c[0]=='csrfmiddlewaretoken' for c in controles.campos))

    def test_matricula_y_extraordinarias_comparten_navegacion(self):
        self.client.force_login(self.usuarios['DIRECTORA'])
        for nombre in ('matricula_secretaria','autorizar_clase_extraordinaria'):
            respuesta=self.client.get(reverse(nombre))
            self.assertEqual(respuesta.status_code,200)
            self.assertContains(respuesta,'id="menu-app"')
            self.assertNotContains(respuesta,'href="#"')

    def test_mis_cursos_vacio_se_conserva(self):
        usuario=Usuario.objects.create_user('sin-cursos-ui','sin-cursos@example.test','clave',rol='MAESTRO')
        self.client.force_login(usuario)
        self.assertContains(self.client.get(reverse('mis_cursos')),'No tiene cursos asignados')

    def test_login_no_simula_recuperacion_inexistente(self):
        self.client.logout()
        respuesta=self.client.get(reverse('login'))
        self.assertNotContains(respuesta,'href="#"')
        self.assertContains(respuesta,'Solicite ayuda a la administración')

    def test_inicio_exige_autenticacion(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('dashboard')),'/login/?next=/',fetch_redirect_response=False)
