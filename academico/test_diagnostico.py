"""Diagnóstico técnico sin exposición de datos; solo SQLite de pruebas."""
from datetime import date
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from core.models import Usuario
from .models import Estudiante


class DiagnosticoSeguroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user('diagnostico', 'diagnostico@example.test', 'clave', rol='ADMINISTRADOR')
        cls.payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
        Estudiante.objects.create(codigo_estudiante='DIAG-1', nombres=cls.payload,
                                  apellidos='<b>Dato privado</b>', fecha_ingreso=date(2026, 1, 1), estado='ACTIVO')

    def test_datos_personales_no_se_exponen_ni_interpretan_como_html(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get('/probar-conexion/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'text/plain; charset=utf-8')
        self.assertEqual(respuesta['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', respuesta['Cache-Control'])
        self.assertEqual(respuesta.content.decode(), 'Conexión verificada. Total de estudiantes: 1.')
        for dato in (self.payload, 'Dato privado', 'DIAG-1', '<script', '<img'):
            self.assertNotContains(respuesta, dato)

    def test_permisos_antes_de_consultar_estudiantes(self):
        self.assertEqual(self.client.get('/probar-conexion/').status_code, 302)
        for rol in ('MAESTRO', 'ESTUDIANTE', 'PASTOR_PRINCIPAL'):
            self.usuario.rol = rol
            self.usuario.save(update_fields=['rol'])
            self.client.force_login(self.usuario)
            with patch('academico.views.Estudiante.objects.count') as consulta:
                self.assertEqual(self.client.get('/probar-conexion/').status_code, 403)
                consulta.assert_not_called()
        for rol in ('SECRETARIA', 'DIRECTORA', 'ADMINISTRADOR'):
            self.usuario.rol = rol
            self.usuario.save(update_fields=['rol'])
            self.client.force_login(self.usuario)
            self.assertEqual(self.client.get('/probar-conexion/').status_code, 200)

    def test_diagnostico_solo_lectura(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post('/probar-conexion/').status_code, 405)
        self.assertEqual(self.client.head('/probar-conexion/').status_code, 200)

    def test_error_de_base_no_revela_detalles(self):
        self.client.force_login(self.usuario)
        with patch('academico.views.Estudiante.objects.count', side_effect=DatabaseError('detalle-interno-privado')):
            respuesta = self.client.get('/probar-conexion/')
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta['Content-Type'], 'text/plain; charset=utf-8')
        self.assertNotContains(respuesta, 'detalle-interno-privado', status_code=503)
