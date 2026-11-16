"""Pruebas esenciales de cuentas. SQLite efímero y personas ficticias únicamente."""
from datetime import date

from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse

from academico.models import Estudiante, Maestro
from .models import Usuario
from .usuarios_servicios import guardar_cuenta


class UsuariosInstitucionalesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin=Usuario.objects.create_user('admin-usuarios','admin-usuarios@example.test','Ficticia-Admin-72!',rol='ADMINISTRADOR')
        cls.cuenta=Usuario.objects.create_user('est-usuarios','est-usuarios@example.test','Ficticia-Inicial-72!',rol='ESTUDIANTE')
        cls.estudiante=Estudiante.objects.create(codigo_estudiante='USU-FICTICIO-1',nombres='Estudiante ficticio',apellidos='Cuentas',
            correo=cls.cuenta.correo_acceso,fecha_ingreso=date(2026,1,1),estado='ACTIVO')
        cls.docente=Usuario.objects.create_user('doc-usuarios','doc-usuarios@example.test','Ficticia-Doc-72!',rol='MAESTRO')
        cls.maestro=Maestro.objects.create(usuario=cls.docente,nombres='Docente ficticio',apellidos='Conservado',pais='SV',estado='ACTIVO')

    def login(self):self.client.force_login(self.admin)

    def datos(self,**cambios):
        return {'numero_usuario':self.cuenta.numero_usuario,'correo_acceso':self.cuenta.correo_acceso,'rol':'ESTUDIANTE','estado_cuenta':'ACTIVA'}|cambios

    def rutas(self):
        return [reverse('usuarios'),reverse('usuarios_nuevo'),reverse('usuarios_editar',args=[self.cuenta.pk]),
                reverse('usuarios_vincular',args=[self.cuenta.pk]),reverse('usuarios_restablecer',args=[self.cuenta.pk])]

    def test_permisos_exclusivos_get_post_y_servicio(self):
        for url in self.rutas():self.assertEqual(self.client.get(url).status_code,302)
        for rol in ('SECRETARIA','DIRECTORA','MAESTRO','ESTUDIANTE','PASTOR_PRINCIPAL'):
            usuario=Usuario.objects.create_user('permiso-'+rol,rol+'@example.test','Ficticia-Acceso-72!',rol=rol)
            self.client.force_login(usuario)
            for url in self.rutas():
                self.assertEqual(self.client.get(url).status_code,403)
                self.assertEqual(self.client.post(url,self.datos()).status_code,403)
            with self.assertRaises(PermissionDenied):guardar_cuenta(actor=usuario,usuario_id=self.cuenta.pk,datos=self.datos())
        self.admin.estado_cuenta='INACTIVA';self.admin.save(update_fields=['estado_cuenta'])
        self.client.force_login(self.admin)
        self.assertIn(self.client.get(reverse('usuarios')).status_code,(302,403))

    def test_creacion_roles_sin_privilegios_y_sin_vinculo_automatico(self):
        self.login()
        temporal='Temporal-Cuenta-Nueva-72!'
        datos=self.datos(numero_usuario='cuenta-nueva',correo_acceso='nueva@example.test',password1=temporal,password2=temporal,is_staff='on',is_superuser='on')
        respuesta=self.client.post(reverse('usuarios_nuevo'),datos,follow=True)
        cuenta=Usuario.objects.get(numero_usuario='cuenta-nueva')
        self.assertContains(respuesta,'Cuenta creada')
        self.assertTrue(cuenta.check_password(temporal))
        self.assertTrue(cuenta.debe_cambiar_password)
        self.assertFalse(cuenta.is_staff or cuenta.is_superuser)
        self.assertFalse(Estudiante.objects.filter(usuario=cuenta).exists())
        self.assertNotContains(respuesta,temporal)
        self.assertNotContains(respuesta,cuenta.password)
        respuesta=self.client.post(reverse('usuarios_nuevo'),datos)
        self.assertEqual(Usuario.objects.filter(numero_usuario='cuenta-nueva').count(),1)
        self.assertTrue(respuesta.context['form'].errors)

    def test_busqueda_filtros_edicion_y_duplicados(self):
        self.login()
        respuesta=self.client.get(reverse('usuarios'),{'q':'est-usuarios','rol':'ESTUDIANTE','estado':'ACTIVA'})
        self.assertContains(respuesta,self.cuenta.correo_acceso)
        self.assertNotContains(respuesta,self.docente.correo_acceso)
        url=reverse('usuarios_editar',args=[self.cuenta.pk])
        respuesta=self.client.post(url,self.datos(correo_acceso='actualizado@example.test'),follow=True)
        self.assertContains(respuesta,'Cuenta actualizada')
        self.cuenta.refresh_from_db();self.assertEqual(self.cuenta.correo_acceso,'actualizado@example.test')
        respuesta=self.client.post(url,self.datos(correo_acceso=self.admin.correo_acceso.upper()))
        self.assertContains(respuesta,'correo ya está utilizado')
        self.cuenta.refresh_from_db();self.assertEqual(self.cuenta.correo_acceso,'actualizado@example.test')
        respuesta=self.client.post(url,self.datos(rol='SUPERUSUARIO'))
        self.assertIn('rol',respuesta.context['form'].errors)

    def test_vinculo_explicito_sin_reasignacion_ni_duplicados(self):
        self.login()
        url=reverse('usuarios_vincular',args=[self.cuenta.pk])
        self.client.post(url,{'estudiante':self.estudiante.pk})
        self.estudiante.refresh_from_db();self.assertIsNone(self.estudiante.usuario_id)
        self.assertEqual(self.client.post(url,{'estudiante':self.estudiante.pk,'confirmar':'on'}).status_code,302)
        self.estudiante.refresh_from_db();self.assertEqual(self.estudiante.usuario_id,self.cuenta.pk)
        otra=Usuario.objects.create_user('est-otra','otra@example.test','Ficticia-Otra-72!',rol='ESTUDIANTE')
        respuesta=self.client.post(reverse('usuarios_vincular',args=[otra.pk]),{'estudiante':self.estudiante.pk,'confirmar':'on'})
        self.assertContains(respuesta,'ya tiene una cuenta vinculada')
        segundo=Estudiante.objects.create(codigo_estudiante='USU-FICTICIO-2',nombres='Otro ficticio',apellidos='Cuentas',fecha_ingreso=date(2026,1,1),estado='ACTIVO')
        respuesta=self.client.post(url,{'estudiante':segundo.pk,'confirmar':'on'})
        self.assertContains(respuesta,'ya tiene otro expediente')
        self.assertEqual(Estudiante.objects.filter(usuario=self.cuenta).count(),1)
        respuesta=self.client.post(reverse('usuarios_editar',args=[self.cuenta.pk]),self.datos(rol='MAESTRO'))
        self.assertContains(respuesta,'vinculada a un estudiante')
        self.client.force_login(self.cuenta)
        self.assertContains(self.client.get(reverse('portal_inicio')),self.estudiante.nombres)

    def test_desactivacion_conserva_datos_y_protege_perfil_docente(self):
        self.login()
        antes=list(Maestro.objects.values())
        respuesta=self.client.post(reverse('usuarios_editar',args=[self.cuenta.pk]),self.datos(estado_cuenta='INACTIVA'))
        self.assertEqual(respuesta.status_code,302)
        self.cuenta.refresh_from_db();self.assertFalse(self.cuenta.is_active)
        self.assertFalse(self.client.login(username=self.cuenta.numero_usuario,password='Ficticia-Inicial-72!'))
        self.login()
        respuesta=self.client.post(reverse('usuarios_editar',args=[self.docente.pk]),self.datos(numero_usuario=self.docente.numero_usuario,
            correo_acceso=self.docente.correo_acceso,rol='ESTUDIANTE'))
        self.assertContains(respuesta,'perfil docente')
        self.assertEqual(list(Maestro.objects.values()),antes)

    def test_no_desactiva_bloquea_ni_degrada_ultimo_admin(self):
        self.login()
        for cambios in ({'estado_cuenta':'INACTIVA'},{'estado_cuenta':'BLOQUEADA'},{'rol':'SECRETARIA'}):
            datos=self.datos(numero_usuario=self.admin.numero_usuario,correo_acceso=self.admin.correo_acceso,rol='ADMINISTRADOR')|cambios
            respuesta=self.client.post(reverse('usuarios_editar',args=[self.admin.pk]),datos)
            self.assertContains(respuesta,'último administrador activo')
            self.admin.refresh_from_db();self.assertTrue(self.admin.is_active);self.assertEqual(self.admin.rol,'ADMINISTRADOR')
        otro=Usuario.objects.create_user('segundo-admin','segundo@example.test','Ficticia-Segundo-72!',rol='ADMINISTRADOR')
        datos=self.datos(numero_usuario=self.admin.numero_usuario,correo_acceso=self.admin.correo_acceso,rol='ADMINISTRADOR',estado_cuenta='INACTIVA')
        self.assertRedirects(self.client.post(reverse('usuarios_editar',args=[self.admin.pk]),datos),reverse('login'))
        self.admin.refresh_from_db();self.assertFalse(self.admin.is_active)
        self.assertTrue(Usuario.objects.get(pk=otro.pk).is_active)

    def test_restablecimiento_invalida_sesion_y_exige_cambio_de_password(self):
        anterior=Client();anterior.force_login(self.cuenta)
        self.login()
        temporal='Temporal-Restablecida-72!'
        respuesta=self.client.post(reverse('usuarios_restablecer',args=[self.cuenta.pk]),{'new_password1':temporal,'new_password2':temporal},follow=True)
        self.assertContains(respuesta,'Acceso restablecido')
        self.assertNotContains(respuesta,temporal)
        self.assertEqual(anterior.get(reverse('portal_inicio')).status_code,302)
        self.cuenta.refresh_from_db();self.assertTrue(self.cuenta.check_password(temporal));self.assertTrue(self.cuenta.debe_cambiar_password)
        self.assertTrue(anterior.login(username=self.cuenta.numero_usuario,password=temporal))
        self.assertRedirects(anterior.get(reverse('portal_inicio')),reverse('cambiar_password'))
        respuesta=anterior.post(reverse('cambiar_password'),{'old_password':temporal,'new_password1':temporal,'new_password2':temporal})
        self.assertContains(respuesta,'diferente de la contraseña temporal')
        self.cuenta.refresh_from_db();self.assertTrue(self.cuenta.debe_cambiar_password)
        definitiva='Definitiva-Segura-94!'
        respuesta=anterior.post(reverse('cambiar_password'),{'old_password':temporal,'new_password1':definitiva,'new_password2':definitiva})
        self.assertEqual(respuesta.status_code,302)
        self.cuenta.refresh_from_db();self.assertFalse(self.cuenta.debe_cambiar_password)
        self.assertTrue(self.cuenta.check_password(definitiva))

    def test_admin_clasico_no_elude_protecciones_de_cuentas(self):
        self.admin.is_staff=True;self.admin.is_superuser=True;self.admin.save(update_fields=['is_staff','is_superuser'])
        self.login()
        urls=[reverse('admin:core_usuario_add'),reverse('admin:core_usuario_change',args=[self.admin.pk]),
              reverse('admin:core_usuario_delete',args=[self.admin.pk]),
              reverse('admin:core_usuario_change',args=[self.admin.pk]).replace('/change/','/password/')]
        for url in urls:
            self.assertEqual(self.client.post(url,self.datos(estado_cuenta='INACTIVA')).status_code,403)
        self.admin.refresh_from_db();self.assertTrue(self.admin.is_active)
