"""Acceso LAN opt-in: hosts exactos, CSRF real y configuración de desarrollo aislada."""
import secrets
from django.conf import settings
from django.test import TestCase,SimpleTestCase,Client,RequestFactory,override_settings
from core.models import Usuario
from iniciar_simulacion import opciones_servidor,IP_LAN


class OpcionesLANTests(SimpleTestCase):
    def test_predeterminado_solo_loopback(self):
        opciones=opciones_servidor()
        self.assertEqual(opciones['direccion'],'127.0.0.1:8000')
        self.assertNotIn(IP_LAN,opciones['hosts'])
        self.assertEqual(opciones['origenes_csrf'],[])
        self.assertTrue(opciones['debug'])

    def test_lan_interfaz_y_origen_exactos_sin_comodines(self):
        opciones=opciones_servidor(True)
        self.assertEqual(opciones['direccion'],'192.168.1.154:8000')
        self.assertEqual(opciones['origenes_csrf'],['http://192.168.1.154:8000'])
        self.assertIn(IP_LAN,opciones['hosts'])
        self.assertNotIn('*',opciones['hosts']);self.assertNotIn('0.0.0.0',opciones['hosts'])
        self.assertFalse(opciones['debug'])

    def test_opciones_no_modifican_la_base_ni_las_configuraciones(self):
        antes=settings.DATABASES.copy()
        hosts=settings.ALLOWED_HOSTS[:]
        opciones_servidor(True)
        self.assertEqual(settings.DATABASES,antes);self.assertEqual(settings.ALLOWED_HOSTS,hosts)
        self.assertIn('django.middleware.csrf.CsrfViewMiddleware',settings.MIDDLEWARE)


class CSRFEnLANTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.clave=secrets.token_urlsafe(20)
        cls.usuario=Usuario.objects.create_user('lan-ficticio','lan@example.test',cls.clave,
            rol='SECRETARIA',debe_cambiar_password=False)

    def setUp(self):
        opciones=opciones_servidor(True)
        self.config=override_settings(ALLOWED_HOSTS=opciones['hosts'],
            CSRF_TRUSTED_ORIGINS=opciones['origenes_csrf'],DEBUG=opciones['debug'])
        self.config.enable();self.addCleanup(self.config.disable)
        self.client=Client(enforce_csrf_checks=True)
        self.host='192.168.1.154:8000'
        self.origen='http://'+self.host

    def token(self):
        r=self.client.get('/login/',HTTP_HOST=self.host)
        self.assertEqual(r.status_code,200)
        return self.client.cookies['csrftoken'].value

    def enviar(self,token=None,origen=None):
        datos={'numero_usuario':self.usuario.numero_usuario,'password':self.clave}
        if token is not None:datos['csrfmiddlewaretoken']=token
        return self.client.post('/login/',datos,HTTP_HOST=self.host,HTTP_ORIGIN=origen or self.origen)

    def test_login_lan_con_token_y_origen_correctos(self):
        r=self.enviar(self.token())
        self.assertEqual(r.status_code,302)
        self.assertEqual(self.client.session['_auth_user_id'],str(self.usuario.pk))

    def test_sin_token_no_autentica(self):
        self.token();self.assertEqual(self.enviar().status_code,403)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_token_incorrecto_no_autentica(self):
        self.token();self.assertEqual(self.enviar('a'*64).status_code,403)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_origen_otro_equipo_rechazado_aun_con_token(self):
        self.assertEqual(self.enviar(self.token(),'http://192.168.1.155:8000').status_code,403)

    def test_origen_otro_puerto_rechazado_aun_con_token(self):
        self.assertEqual(self.enviar(self.token(),'http://192.168.1.154:8001').status_code,403)

    def test_host_ajeno_rechazado(self):
        for host in ('ejemplo.test:8000','192.168.1.155:8000','192.168.1.154.ejemplo.test:8000'):
            with self.subTest(host=host):self.assertEqual(self.client.get('/login/',HTTP_HOST=host).status_code,400)

    def test_ip_lan_rechazada_en_modo_predeterminado(self):
        with override_settings(ALLOWED_HOSTS=opciones_servidor()['hosts']):
            self.assertEqual(self.client.get('/login/',HTTP_HOST=self.host).status_code,400)

    def test_hosts_locales_se_conservan(self):
        for host in ('127.0.0.1:8000','localhost:8000'):
            self.assertEqual(self.client.get('/login/',HTTP_HOST=host).status_code,200)

    def test_errores_lan_no_muestran_depuracion(self):
        r=self.client.get('/ruta-inexistente-simulacion/',HTTP_HOST=self.host)
        self.assertEqual(r.status_code,404)
        self.assertNotContains(r,'URL patterns',status_code=404)
        self.assertNotContains(r,'Traceback',status_code=404)

    def test_estaticos_disponibles_con_depuracion_desactivada(self):
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.core.handlers.wsgi import WSGIHandler
        handler=StaticFilesHandler(WSGIHandler())
        for ruta in ('/static/css/sistema_visual.css','/static/img/vidasys.png','/static/js/navegacion.js'):
            request=RequestFactory().get(ruta,HTTP_HOST=self.host)
            respuesta=handler.get_response(request)
            self.assertEqual(respuesta.status_code,200)
            respuesta.close()
