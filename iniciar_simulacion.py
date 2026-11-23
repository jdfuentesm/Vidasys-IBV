"""F7.1. Ejecutar explícitamente; no lee .env y nunca conecta a PostgreSQL."""
import argparse
import os
import sys

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--semilla',type=int,default=711)
    parser.add_argument('--fecha',help='Fecha de referencia ISO; por defecto hoy en El Salvador.')
    parser.add_argument('--comprobar',action='store_true',help='Generar y validar, sin iniciar servidor.')
    args=parser.parse_args()
    # Debe fijarse antes de importar Django; no se heredan settings de producción.
    if 'django.conf' in sys.modules:raise RuntimeError('Ejecute el lanzador en un proceso Python nuevo.')
    os.environ['DJANGO_SETTINGS_MODULE']='simulacion.settings'
    sys.dont_write_bytecode=True
    import django
    django.setup()
    from django.core.management import call_command
    from django.utils import timezone
    from datetime import date
    from simulacion.entorno import preparar_tablas
    from django.db import connection
    from simulacion.generador import verificar_memoria,generar
    from simulacion.validacion import validar
    verificar_memoria()
    referencia=date.fromisoformat(args.fecha) if args.fecha else timezone.localdate()
    print("Preparando esquema exclusivo SQLite :memory:...",flush=True)
    preparar_tablas()
    try:
        print("Generando 40 estudiantes y operaciones ficticias mediante servicios institucionales...",flush=True)
        escenario=generar(semilla=args.semilla,referencia=referencia)
        validacion=validar(escenario)
        import json
        print(json.dumps({'resumen':escenario.resumen,'esperados':escenario.esperados(),
            'validacion':validacion},ensure_ascii=False,indent=2,default=str),flush=True)
        print('\nDATOS FICTICIOS · SOLO SQLITE EN MEMORIA',flush=True)
        for nombre in escenario.credenciales:print(nombre,flush=True)
        print('Contraseña temporal común (no guardar en Git):',escenario.password,flush=True)
        print('http://127.0.0.1:8000/login/ · Ctrl+C descarta los datos.',flush=True)
        if not args.comprobar:
            call_command('runserver','127.0.0.1:8000',use_reloader=False,use_threading=False)
    finally:connection.close()

if __name__=='__main__':main()
