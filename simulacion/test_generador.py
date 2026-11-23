"""Guardas sin conexión y pruebas integrales en procesos SQLite :memory: separados."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from .generador import verificar_memoria,mes
from datetime import date

ROOT=Path(__file__).resolve().parent.parent


class GuardasSimulacionTests(SimpleTestCase):
    def comprobar(self,engine,nombre,vendor='sqlite',conexion=':memory:'):
        with patch('simulacion.generador.settings',SimpleNamespace(DATABASES={'default':{'ENGINE':engine,'NAME':nombre}})),\
             patch('simulacion.generador.connection',SimpleNamespace(vendor=vendor,settings_dict={'NAME':conexion})):
            verificar_memoria()

    def test_solo_memoria_exacta(self):self.comprobar('django.db.backends.sqlite3',':memory:')
    def test_rechaza_postgresql_sin_conectar(self):
        with self.assertRaises(RuntimeError):self.comprobar('django.db.backends.postgresql','ensayo',vendor='postgresql')
    def test_rechaza_sqlite_archivo(self):
        with self.assertRaises(RuntimeError):self.comprobar('django.db.backends.sqlite3','ensayo.sqlite3')
    def test_rechaza_uri_memoria_no_explicitamente_autorizada(self):
        with self.assertRaises(RuntimeError):self.comprobar('django.db.backends.sqlite3','file:memorydb?mode=memory')
    def test_rechaza_conexion_divergente(self):
        with self.assertRaises(RuntimeError):self.comprobar('django.db.backends.sqlite3',':memory:',conexion='ensayo.sqlite3')
    def test_meses_cruzan_anio(self):self.assertEqual(mes(date(2027,1,31),-2),date(2026,11,1))
    def test_configuracion_no_importa_config_productivo(self):
        import ast
        tree=ast.parse((ROOT/'simulacion/settings.py').read_text())
        imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertNotIn('config.settings',imports);self.assertNotIn('decouple',imports)


class GeneracionIntegralTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ejecuciones=[]
        for _ in range(2):
            r=subprocess.run([sys.executable,'-B','iniciar_simulacion.py','--comprobar','--fecha','2026-11-22','--semilla','711'],
                cwd=ROOT,capture_output=True,text=True,timeout=180)
            if r.returncode:raise AssertionError('Falló simulación: '+r.stderr[-3500:])
            texto=r.stdout[r.stdout.index('{'):]
            cls.ejecuciones.append(json.JSONDecoder().raw_decode(texto)[0])
        cls.d=cls.ejecuciones[0]

    def test_cantidades_exactas(self):
        for tabla,n in [('estudiante',40),('maestro',6),('materia',12),('matricula',40),('obligacion',240),('pago',132),('donante',5),('solicitud_egreso',15),('cajas_cerradas',10),('cajas_abiertas',2)]:
            with self.subTest(tabla=tabla):self.assertEqual(self.d['resumen'][tabla],n)
        self.assertEqual(self.d['resumen']['estudiantes_por_anio'],{'primero':20,'segundo':20})
    def test_reproducible_con_misma_semilla_y_fecha(self):
        self.assertEqual(self.ejecuciones[0]['resumen']['huella_datos_sha256'],self.ejecuciones[1]['resumen']['huella_datos_sha256'])
        self.assertEqual(self.ejecuciones[0]['esperados'],self.ejecuciones[1]['esperados'])
    def test_conciliacion_independiente_y_regresion_f7(self):
        self.assertEqual(self.d['validacion']['diferencias'],[])
        self.assertEqual(self.d['validacion']['estado'],'CONCILIADO')
        self.assertGreater(self.d['validacion']['comprobaciones'],600)
        for campo,esperado in [('ingresos','2764.00'),('egresos','86.00'),('resultado','2678.00'),('saldo','1952.00'),('cobertura','640.00'),('cargo_estudiantes','1312.00')]:
            with self.subTest(campo=campo):self.assertEqual(self.d['esperados'][campo],esperado)
    def test_academico_con_cierres_y_notas_provisionales(self):
        self.assertEqual(self.d['resumen']['cursos_por_estado'],{'FINALIZADO':6,'ACTIVO':6})
        self.assertGreater(self.d['resumen']['resultados_academicos']['APROBADA'],0)
        self.assertGreater(self.d['resumen']['resultados_academicos']['REPROBADA_ACADEMICAMENTE'],0)
        self.assertEqual(self.d['resumen']['resultados_academicos']['REPROBADA_POR_INASISTENCIA'],12)
        self.assertEqual(self.d['resumen']['asistencia'],1236)
    def test_ocho_reportes_tres_formatos_y_consultas_reales(self):
        self.assertEqual(len(self.d['validacion']['http']),24)
        self.assertEqual(set(self.d['validacion']['http'].values()),{200})
        self.assertTrue(all(n>0 for n in self.d['validacion']['consultas_reportes'].values()))
    def test_solvencia_y_mora_sin_forzar_estados(self):
        self.assertEqual(self.d['validacion']['solventes'],31);self.assertEqual(self.d['validacion']['insolventes'],9)
        self.assertEqual(self.d['resumen']['convenios_por_estado'],{'ACTIVO':3,'CUMPLIDO':1})
        self.assertTrue(any('INCUMPLIDO' in x for x in self.d['validacion']['limitaciones']))
    def test_no_exporta_password_en_resumen(self):
        texto=json.dumps(self.d)
        self.assertNotIn('Contraseña temporal',texto);self.assertNotIn('password',texto)

class RollbackGeneradorTests(SimpleTestCase):
    def test_fallo_revierte_catalogo_y_restaura_reloj(self):
        codigo='''
import os,secrets
os.environ['DJANGO_SETTINGS_MODULE']='simulacion.settings'
import django
django.setup()
from django.utils import timezone
from django.core.exceptions import ValidationError
from core.models import Usuario
from simulacion.entorno import preparar_tablas
from simulacion.generador import Escenario,generar
from unittest.mock import patch
preparar_tablas()
original=timezone.datetime
def fallo(self):
    Usuario.objects.create_user('sim-error','error@example.test',secrets.token_urlsafe(20),rol='SECRETARIA')
    raise ValidationError('Fallo deliberado del generador')
try:
    with patch.object(Escenario,'catalogos',fallo):generar()
except ValidationError:
    assert Usuario.objects.count()==0
    assert timezone.datetime is original
else:raise AssertionError('No abortó el generador')
'''
        r=subprocess.run([sys.executable,'-B','-c',codigo],cwd=ROOT,capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr[-2000:])
