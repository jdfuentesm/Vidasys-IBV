"""No abren PostgreSQL. Simulación del guardián y flujo real sobre SQLite efímero."""
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings

from academico.models import Calificacion, CicloAcademico, InscripcionCurso, Matricula
from academico.tests import CalificacionesTests
from core import ensayo_seguro as seguro
from core.management.commands import ensayo_calificaciones as flujo


class GuardiaEnsayoTests(SimpleTestCase):
    def setUp(self):
        self.cfg = SimpleNamespace(ENSAYO_ACTIVO=True, DATABASE_ROUTERS=[],
            DATABASES={"default": {"NAME": seguro.BASE}})
        self.connection = SimpleNamespace(alias="default", vendor="postgresql",
            settings_dict={"NAME": seguro.BASE})
        self.cursor = Mock()
        self.cursor.fetchone.return_value = (seguro.BASE,)
        self.execute = Mock()
        self.context = {"connection": self.connection, "cursor": self.cursor}
        self.entorno = patch.dict(os.environ, {"DB_NAME": seguro.BASE})
        self.entorno.start()
        self.config = patch.object(seguro, "settings", self.cfg)
        self.config.start()
        self.addCleanup(self.entorno.stop)
        self.addCleanup(self.config.stop)

    def test_base_configurada_incorrecta_aborta_sin_sentencias(self):
        self.connection.settings_dict["NAME"] = "gestion_ibv"
        with self.assertRaises(seguro.EnsayoInseguro):
            seguro.guardia_sql(self.execute, 'INSERT INTO usuario VALUES (1)', None, False, self.context)
        self.execute.assert_not_called()

    def test_variable_entorno_incorrecta_aborta(self):
        with patch.dict(os.environ, {"DB_NAME": "gestion_ibv"}):
            with self.assertRaises(seguro.EnsayoInseguro):
                seguro.comprobar_configuracion(self.connection)

    def test_conexion_real_incorrecta_impide_escritura(self):
        self.cursor.fetchone.return_value = ("gestion_ibv",)
        with seguro.permitir_escrituras(), self.assertRaises(seguro.EnsayoInseguro):
            seguro.guardia_sql(self.execute, 'INSERT INTO usuario VALUES (1)', None, False, self.context)
        self.assertEqual(self.execute.call_count, 1)
        self.assertTrue(self.execute.call_args.args[0].startswith('SELECT'))

    def test_rechaza_alias_adicional_router_y_motor(self):
        for cambio in ('alias', 'router', 'motor', 'config'):
            with self.subTest(cambio=cambio):
                conn = deepcopy(self.connection)
                original = deepcopy(self.cfg.DATABASES)
                if cambio == 'alias': conn.alias = 'principal'
                if cambio == 'router': self.cfg.DATABASE_ROUTERS = ['router']
                if cambio == 'motor': conn.vendor = 'sqlite'
                if cambio == 'config': self.cfg.DATABASES['principal'] = {"NAME": "gestion_ibv"}
                with self.assertRaises(seguro.EnsayoInseguro):
                    seguro.comprobar_configuracion(conn)
                self.cfg.DATABASES = original
                self.cfg.DATABASE_ROUTERS = []

    def test_denegacion_predeterminada_y_restauracion_del_contexto(self):
        for dentro in (False, True, False):
            if dentro:
                with seguro.permitir_escrituras():
                    seguro.guardia_sql(self.execute, 'UPDATE usuario SET rol=%s', ['MAESTRO'], False, self.context)
            else:
                with self.assertRaises(seguro.EnsayoInseguro):
                    seguro.guardia_sql(self.execute, 'UPDATE usuario SET rol=%s', ['MAESTRO'], False, self.context)
        self.assertEqual(sum(c.args[0].startswith('UPDATE') for c in self.execute.call_args_list), 1)

    def test_rechaza_ddl_y_with_aun_con_permiso(self):
        for sentencia in ('DROP TABLE usuario', 'CREATE TABLE x(id int)', 'ALTER TABLE usuario ADD x int',
                          'TRUNCATE usuario', 'DO $$ BEGIN END $$', 'COPY usuario TO STDOUT',
                          'WITH x AS (DELETE FROM usuario) SELECT 1', 'SET ROLE postgres'):
            with self.subTest(sentencia=sentencia), seguro.permitir_escrituras(), self.assertRaises(seguro.EnsayoInseguro):
                seguro.guardia_sql(self.execute, sentencia, None, False, self.context)

    def test_recomprueba_base_antes_de_cada_sentencia(self):
        with seguro.permitir_escrituras():
            for sentencia in ('SELECT 1', 'INSERT INTO usuario VALUES (1)', 'DELETE FROM usuario WHERE id_usuario=1'):
                seguro.guardia_sql(self.execute, sentencia, None, False, self.context)
        self.assertEqual(self.execute.call_count, 6)
        self.assertTrue(all(self.execute.call_args_list[i].args[0] == 'SELECT pg_catalog.current_database()'
                            for i in (0, 2, 4)))

    def test_comando_normal_rechazado_antes_de_abrir_base(self):
        with patch.object(flujo, 'comprobar_configuracion', side_effect=seguro.EnsayoInseguro('base incorrecta')):
            with self.assertRaises(CommandError):
                call_command('ensayo_calificaciones', 'inspeccionar')


class ManifiestoEnsayoTests(SimpleTestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        self.ruta = Path(self.carpeta.name) / 'ensayo.json.firmado'
        self.datos = {"run_id": seguro.nuevo_id(), "base": seguro.BASE, "huella": "huella-test", "version": 1}

    def test_firma_lectura_y_no_sobrescritura(self):
        seguro.guardar_manifiesto(self.ruta, self.datos, nuevo=True)
        self.assertEqual(seguro.leer_manifiesto(self.ruta, 'huella-test'), self.datos)
        with self.assertRaises(FileExistsError):
            seguro.guardar_manifiesto(self.ruta, self.datos, nuevo=True)

    def test_alteracion_o_servidor_distinto_rechazados(self):
        seguro.guardar_manifiesto(self.ruta, self.datos, nuevo=True)
        with self.assertRaises(seguro.EnsayoInseguro):
            seguro.leer_manifiesto(self.ruta, 'otro-servidor')
        self.ruta.write_text(self.ruta.read_text()[:-2] + 'XX')
        with self.assertRaises(seguro.EnsayoInseguro):
            seguro.leer_manifiesto(self.ruta, 'huella-test')

    def test_ruta_en_repositorio_rechazada(self):
        with self.assertRaises(seguro.EnsayoInseguro):
            seguro.ruta_manifiesto(Path(__file__).parent / 'no-crear.json')

    def test_identificador_y_base_incorrectos_rechazados(self):
        for campo, valor in (("run_id", "cualquier-prefijo"), ("base", "gestion_ibv")):
            datos = dict(self.datos, **{campo: valor})
            with self.assertRaises(seguro.EnsayoInseguro):
                seguro.guardar_manifiesto(self.ruta, datos, nuevo=True)
        self.assertFalse(self.ruta.exists())


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
class FlujoEnsayoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CalificacionesTests.setUpTestData()
        cls.ciclo = CalificacionesTests.cursos[0].ciclo

    def datos(self):
        return {"run_id": seguro.nuevo_id(), "base": seguro.BASE, "huella": "test", "version": 1,
                "fase": "preparando", "registros": []}

    def test_preparar_cuatro_estudiantes_y_no_tocar_ciclo(self):
        antes = CicloAcademico.objects.values().get(pk=self.ciclo.pk)
        datos = self.datos()
        flujo.preparar(datos, self.ciclo.pk)
        self.assertEqual(len(datos['inscripciones']), 4)
        self.assertEqual(len(datos['registros']), 16)
        self.assertEqual(CicloAcademico.objects.values().get(pk=self.ciclo.pk), antes)
        self.assertFalse(Calificacion.objects.filter(inscripcion_id__in=datos['inscripciones']).exists())
        self.assertNotIn('password', str(datos))
        flujo.comprobar_registros(datos)

    def test_flujo_real_masivo_validacion_rollback_cero_pendiente_permisos_y_revision(self):
        datos = self.datos()
        ciclo_antes = CicloAcademico.objects.values().get(pk=self.ciclo.pk)
        existentes = list(InscripcionCurso.objects.order_by('pk').values())
        flujo.preparar(datos, self.ciclo.pk)
        with transaction.atomic():
            flujo.probar(datos)
        flujo.verificar(datos)
        self.assertEqual(datos['fase'], 'probado')
        self.assertEqual(len(datos['registros']), 19)
        self.assertEqual(Calificacion.objects.filter(inscripcion_id__in=datos['inscripciones']).count(), 3)
        flujo.comprobar_registros(datos)
        self.assertEqual(CicloAcademico.objects.values().get(pk=self.ciclo.pk), ciclo_antes)
        self.assertEqual(list(InscripcionCurso.objects.filter(pk__in=[r['id_inscripcion'] for r in existentes]).order_by('pk').values()), existentes)

    def test_marca_modificada_bloquea_limpieza(self):
        datos = self.datos()
        flujo.preparar(datos, self.ciclo.pk)
        registro = next(r for r in datos['registros'] if r['modelo'] == 'academico.matricula')
        Matricula.objects.filter(pk=registro['id']).update(numero_matricula='OTRO-REGISTRO')
        with self.assertRaises(seguro.EnsayoInseguro):
            flujo.comprobar_registros(datos)

    def test_registro_faltante_no_autoriza_limpieza_parcial(self):
        datos = self.datos()
        flujo.preparar(datos, self.ciclo.pk)
        datos['registros'][0]['id'] = 99999999
        with self.assertRaises(seguro.EnsayoInseguro):
            flujo.comprobar_registros(datos)

    def test_colision_de_identificador_no_reutiliza_registros(self):
        datos = self.datos()
        flujo.preparar(datos, self.ciclo.pk)
        antes = len(flujo.MODELOS['core.usuario'].objects.all())
        with self.assertRaises(seguro.EnsayoInseguro):
            flujo.preparar(self.datos() | {'run_id': datos['run_id']}, self.ciclo.pk)
        self.assertEqual(flujo.MODELOS['core.usuario'].objects.count(), antes)


class InspeccionCatalogoTests(SimpleTestCase):
    def inspeccion(self, cambio=None):
        from unittest.mock import MagicMock
        cursor = MagicMock()
        conexion = MagicMock()
        conexion.cursor.return_value.__enter__.return_value = cursor
        # fetchall se usa únicamente para el inventario de tablas.
        cursor.fetchall.return_value = [(t,) for t in seguro.TABLAS]
        resultados = [
            (seguro.BASE, 180000, 'pg_catalog'), (False, False, False, False, False),
            (0,), (0,), (0,),  # otras bases, servidores externos, extensiones
            (0,), (0,), (0,), (0,), (0,),  # triggers, reglas, tipos, funciones, FK
            (123, 'direccion-simulada', 5432),
        ]
        if cambio:
            resultados[cambio[0]] = cambio[1]
        cursor.fetchone.side_effect = resultados
        with patch.object(seguro, 'comprobar_configuracion'):
            resultado = seguro.inspeccionar(conexion)
        self.assertTrue(all(c.args[0].strip().startswith('SELECT') for c in cursor.execute.call_args_list))
        return resultado

    def test_catalogo_compatible_solo_consulta_metadatos(self):
        self.assertEqual(len(self.inspeccion()), 64)

    def test_bloquea_postgresql_distinto_y_schema_incorrecto(self):
        for fila in ((seguro.BASE, 170000, 'pg_catalog'), (seguro.BASE, 180000, 'public'),
                     ('gestion_ibv', 180000, 'pg_catalog')):
            with self.subTest(fila=fila), self.assertRaises(seguro.EnsayoInseguro):
                self.inspeccion((0, fila))

    def test_no_sigue_si_no_puede_demostrar_aislamiento(self):
        cambios = [(1, (True, False, False, False, False))]
        cambios += [(i, (1,)) for i in range(2, 10)]
        for cambio in cambios:
            with self.subTest(cambio=cambio), self.assertRaises(seguro.EnsayoInseguro):
                self.inspeccion(cambio)


class DependenciasEnsayoTests(SimpleTestCase):
    def referencias(self, cantidad):
        from unittest.mock import MagicMock
        conexion = MagicMock()
        cursor = conexion.cursor.return_value.__enter__.return_value
        conexion.ops.quote_name.side_effect = lambda nombre: '"' + nombre + '"'
        cursor.fetchall.return_value = [('public', 'otra_tabla', [1], [1], 'usuario', 123,
                                        ['actor_id'], ['id_usuario'])]
        cursor.fetchone.return_value = (cantidad,)
        datos = {'registros': [{'modelo': 'core.usuario', 'id': 11, 'marcas': {}}]}
        with patch.object(flujo, 'connection', conexion):
            flujo.comprobar_dependencias(datos)
        self.assertTrue(all(c.args[0].lstrip().startswith('SELECT') for c in cursor.execute.call_args_list))

    def test_dependencia_ajena_bloquea_limpieza(self):
        with self.assertRaises(seguro.EnsayoInseguro):
            self.referencias(1)

    def test_sin_dependencia_ajena_no_modifica_nada(self):
        self.referencias(0)


class BorradoExactoEnsayoTests(SimpleTestCase):
    def test_solo_claves_del_manifiesto_en_orden_inverso(self):
        from unittest.mock import MagicMock
        conexion = MagicMock()
        conexion.ops.quote_name.side_effect = lambda n: '"' + n + '"'
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        datos = {'registros': [{'modelo': 'core.usuario', 'id': 901},
                              {'modelo': 'academico.maestro', 'id': 902}]}
        with patch.object(flujo, 'connection', conexion):
            flujo.limpiar_registros(datos)
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertEqual(cursor.execute.call_args_list[0].args,
                         ('DELETE FROM public."maestro" WHERE "id_maestro"=%s', [902]))
        self.assertEqual(cursor.execute.call_args_list[1].args,
                         ('DELETE FROM public."usuario" WHERE "id_usuario"=%s', [901]))

    def test_cantidad_inesperada_interrumpe_el_borrado(self):
        from unittest.mock import MagicMock
        conexion = MagicMock()
        conexion.ops.quote_name.side_effect = lambda n: '"' + n + '"'
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.rowcount = 0
        datos = {'registros': [{'modelo': 'core.usuario', 'id': 901},
                              {'modelo': 'academico.maestro', 'id': 902}]}
        with patch.object(flujo, 'connection', conexion), self.assertRaises(seguro.EnsayoInseguro):
            flujo.limpiar_registros(datos)
        self.assertEqual(cursor.execute.call_count, 1)


class ImportacionSeguraTests(SimpleTestCase):
    def test_settings_y_check_no_abren_ninguna_conexion(self):
        import subprocess
        import sys
        codigo = '''
import os
os.environ['DJANGO_SETTINGS_MODULE']='config.settings_ensayo'
os.environ['DB_NAME']='gestion_ibv_ensayo'
from unittest.mock import patch
with patch('django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection', side_effect=AssertionError('No se permite conectar')):
 import django
 django.setup()
 from django.core.management import call_command
 call_command('check', verbosity=0)
 from django.conf import settings
 assert settings.ENSAYO_ACTIVO
 assert set(settings.DATABASES)=={'default'}
'''
        resultado = subprocess.run([sys.executable, '-B', '-c', codigo], capture_output=True, text=True)
        self.assertEqual(resultado.returncode, 0, 'La configuración/check intentó abrir una conexión o falló al importar.')
