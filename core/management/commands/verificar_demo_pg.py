from django.core.management.base import BaseCommand
from core.demo_preflight import verificar_esquema_demo


class Command(BaseCommand):
    help='Verificar esquema demo mediante consultas de catálogo, sin modificar datos.'

    def handle(self,*args,**options):
        verificar_esquema_demo()
        self.stdout.write(self.style.SUCCESS('Esquema demo: tablas, unicidades, vistas, funciones, columna calculada, calendario JSONB y secuencia presentes.'))
