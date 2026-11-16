"""Recorrido estudiantil con datos ficticios y SQLite efímero exclusivamente."""
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.models import Usuario
from . import test_flujo as fixtures
from .flujo import matricular
from .models import Asistencia, Calificacion, Estudiante, InscripcionCurso, Maestro, Matricula


class EstudiantesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.FlujoAcademicoTests.setUpTestData()
        base = fixtures.FlujoAcademicoTests
        cls.secretaria, cls.docente, cls.directora = base.secretaria, base.docente, base.directora
        cls.estudiante, cls.ciclo, cls.maestro = base.estudiante, base.ciclo, base.maestro
        cls.cursos = base.cursos

    def datos(self, **cambios):
        datos = {'codigo_estudiante': 'NUEVO-001', 'nombres': 'Ana María', 'apellidos': 'López Pérez',
                 'fecha_nacimiento': '2000-05-12', 'fecha_ingreso': '2026-01-01',
                 'telefono': '7000-0000', 'correo': 'ana@example.test', 'direccion': 'Dirección ficticia', 'estado': 'ACTIVO'}
        return datos | cambios

    def urls(self):
        pk = self.estudiante.pk
        return [reverse('estudiantes'), reverse('estudiante_nuevo'), reverse('estudiante_editar', args=[pk]),
                reverse('estudiante_expediente', args=[pk]), reverse('estudiante_matricular', args=[pk])]

    def login(self):
        self.client.force_login(self.secretaria)

    def test_permisos_servidor_get_post_y_anonimo(self):
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url, self.datos()).status_code, 302)
        for rol in ('MAESTRO', 'ESTUDIANTE', 'PASTOR_PRINCIPAL'):
            usuario = Usuario.objects.create_user('perm-'+rol, rol+'@example.test', 'clave', rol=rol)
            self.client.force_login(usuario)
            for url in self.urls():
                with self.subTest(rol=rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, self.datos()).status_code, 403)
        self.assertEqual(Estudiante.objects.count(), 1)
        self.assertFalse(Matricula.objects.exists())

    def test_roles_autorizados_e_inactivos(self):
        admin = Usuario.objects.create_user('admin-est', 'admin-est@example.test', 'clave', rol='ADMINISTRADOR')
        for usuario in (admin, self.secretaria, self.directora):
            self.client.force_login(usuario)
            for url in self.urls():
                self.assertEqual(self.client.get(url).status_code, 200)
        self.secretaria.estado_cuenta = 'INACTIVA'
        self.secretaria.save()
        self.client.force_login(self.secretaria)
        for url in self.urls():
            self.assertIn(self.client.post(url, self.datos()).status_code, (302, 403))
        self.assertEqual(Estudiante.objects.count(), 1)

    def test_registro_completo_redirige_a_expediente_sin_crear_cuenta(self):
        self.login()
        antes = list(Maestro.objects.values())
        cuentas = Usuario.objects.count()
        respuesta = self.client.post(reverse('estudiante_nuevo'), self.datos(usuario=self.docente.pk), follow=True)
        estudiante = Estudiante.objects.get(codigo_estudiante='NUEVO-001')
        self.assertRedirects(respuesta, reverse('estudiante_expediente', args=[estudiante.pk]))
        self.assertContains(respuesta, 'Estudiante registrado')
        self.assertContains(respuesta, 'Ana María López Pérez')
        self.assertIsNone(estudiante.usuario_id)
        self.assertEqual(Usuario.objects.count(), cuentas)
        self.assertEqual(list(Maestro.objects.values()), antes)
        self.assertFalse(Matricula.objects.exists())

    def test_duplicados_codigo_y_datos_invalidos(self):
        self.login()
        for codigo in (self.estudiante.codigo_estudiante, ' '+self.estudiante.codigo_estudiante.lower()+' '):
            respuesta = self.client.post(reverse('estudiante_nuevo'), self.datos(codigo_estudiante=codigo))
            self.assertContains(respuesta, 'Ya existe un estudiante con este código')
        respuesta = self.client.post(reverse('estudiante_nuevo'), self.datos(nombres=' ', correo='incorrecto', fecha_nacimiento='2030-01-01'))
        self.assertIn('nombres', respuesta.context['form'].errors)
        self.assertIn('correo', respuesta.context['form'].errors)
        self.assertIn('fecha_nacimiento', respuesta.context['form'].errors)
        self.assertEqual(Estudiante.objects.count(), 1)

    def test_duplicado_concurrente_presenta_error_sin_guardado_parcial(self):
        self.login()
        with patch.object(Estudiante, 'save', side_effect=IntegrityError('simulado')):
            respuesta = self.client.post(reverse('estudiante_nuevo'), self.datos())
        self.assertContains(respuesta, 'hay un registro duplicado o datos incompatibles')
        self.assertEqual(Estudiante.objects.count(), 1)

    def test_edicion_preserva_identidad_usuario_historial_y_docente(self):
        self.login()
        matricula, inscripciones, _ = matricular(estudiante=self.estudiante, ciclo=self.ciclo,
            numero_matricula='EST-M1', fecha_matricula=self.ciclo.fecha_inicio)
        sesion = fixtures.FlujoAcademicoTests.sesion(self)
        Asistencia.objects.create(inscripcion=inscripciones[0], sesion=sesion, estado_asistencia='PRESENTE')
        Calificacion.objects.create(inscripcion=inscripciones[0], **dict(zip(Calificacion.COMPONENTES, [40,20,20,20,0,75,75,75,75])))
        InscripcionCurso.objects.filter(pk=inscripciones[0].pk).update(estado='REPROBADA_POR_INASISTENCIA', fecha_cierre='2026-02-01')
        modelos = (Matricula, InscripcionCurso, Asistencia, Calificacion, Maestro, Usuario)
        antes = [list(m.objects.values()) for m in modelos]
        respuesta = self.client.post(reverse('estudiante_editar', args=[self.estudiante.pk]), self.datos(
            codigo_estudiante='MANIPULADO', fecha_ingreso='2030-01-01', usuario=self.docente.pk,
            nombres='Nombre corregido', estado='INACTIVO'), follow=True)
        self.assertContains(respuesta, 'Información del estudiante actualizada')
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.nombres, 'Nombre corregido')
        self.assertEqual(self.estudiante.codigo_estudiante, 'FLUJO-E1')
        self.assertEqual(str(self.estudiante.fecha_ingreso), '2026-01-01')
        self.assertIsNone(self.estudiante.usuario_id)
        self.assertEqual(antes, [list(m.objects.values()) for m in modelos])
        self.assertContains(respuesta, 'REPROBADA_POR_INASISTENCIA')

    def test_busqueda_nombre_completo_filtros_y_paginacion(self):
        self.login()
        ana = Estudiante.objects.create(**{k:v for k,v in self.datos().items() if k not in ('usuario',)})
        respuesta = self.client.get(reverse('estudiantes'), {'q': 'Ana López', 'estado': 'ACTIVO'})
        self.assertContains(respuesta, 'López Pérez, Ana María')
        self.assertNotContains(respuesta, self.estudiante.codigo_estudiante)
        self.assertContains(self.client.get(reverse('estudiantes'), {'q': 'no-existe'}), 'No se encontraron estudiantes')
        matricular(estudiante=ana, ciclo=self.ciclo, numero_matricula='BUS-M', fecha_matricula=self.ciclo.fecha_inicio)
        respuesta = self.client.get(reverse('estudiantes'), {'ciclo': self.ciclo.pk})
        self.assertEqual(list(respuesta.context['pagina']), [ana])
        for n in range(21):
            Estudiante.objects.create(codigo_estudiante=f'P-{n}', nombres='Ana', apellidos='López', fecha_ingreso='2026-01-01', estado='ACTIVO')
        respuesta = self.client.get(reverse('estudiantes'), {'q': 'Ana', 'estado': 'ACTIVO', 'page': '2'})
        self.assertEqual(respuesta.context['pagina'].number, 2)
        self.assertContains(respuesta, 'q=Ana&amp;estado=ACTIVO&amp;page=1')

    def test_expediente_matricula_integrada_fija_estudiante_e_idempotencia(self):
        self.login()
        otro = Estudiante.objects.create(codigo_estudiante='OTRO', nombres='Otro', apellidos='Ficticio', fecha_ingreso='2026-01-01', estado='ACTIVO')
        url = reverse('estudiante_matricular', args=[self.estudiante.pk])
        respuesta = self.client.get(reverse('estudiante_expediente', args=[self.estudiante.pk]))
        self.assertContains(respuesta, url)
        antes = list(Maestro.objects.values())
        datos = {'estudiante': otro.pk, 'ciclo': self.ciclo.pk, 'numero_matricula': 'EST-MAT', 'fecha_matricula': '2026-01-01'}
        respuesta = self.client.post(url, datos)
        self.assertContains(respuesta, 'Matrícula registrada con sus seis materias')
        self.assertEqual(Matricula.objects.get().estudiante_id, self.estudiante.pk)
        self.assertEqual(InscripcionCurso.objects.count(), 6)
        self.client.post(url, datos)
        self.assertEqual(Matricula.objects.count(), 1)
        self.assertEqual(InscripcionCurso.objects.count(), 6)
        self.assertEqual(list(Maestro.objects.values()), antes)
        respuesta = self.client.get(reverse('estudiante_expediente', args=[self.estudiante.pk]))
        self.assertContains(respuesta, 'EST-MAT')
        for curso in fixtures.FlujoAcademicoTests.cursos:
            self.assertContains(respuesta, curso.materia.nombre)
        self.assertNotContains(respuesta, 'Saldo')

    def test_objetos_inexistentes_y_navegacion(self):
        self.login()
        for nombre in ('estudiante_expediente', 'estudiante_editar', 'estudiante_matricular'):
            self.assertEqual(self.client.get(reverse(nombre, args=[999999])).status_code, 404)
        self.assertContains(self.client.get(reverse('dashboard')), reverse('estudiantes'))
