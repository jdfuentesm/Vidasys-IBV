from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import ProgrammingError

from core.models import Usuario


class Command(BaseCommand):
    help = (
        "Crea los permisos académicos y configura el grupo para las directoras activas."
    )

    def handle(self, *args, **options):
        app_academica = apps.get_app_config("academico")

        create_permissions(
            app_academica,
            verbosity=0,
        )

        codigos_permitidos = {
            "view_curso",
            "view_materia",
            "view_maestro",
            "view_sesionclase",
            "add_sesionclase",
            "change_sesionclase",
        }

        permisos = Permission.objects.filter(
            content_type__app_label="academico",
            codename__in=codigos_permitidos,
        )

        codigos_encontrados = set(permisos.values_list("codename", flat=True))

        codigos_faltantes = codigos_permitidos - codigos_encontrados

        if codigos_faltantes:
            raise CommandError(
                "No se encontraron los siguientes permisos: "
                + ", ".join(sorted(codigos_faltantes))
            )

        try:
            grupo, creado = Group.objects.get_or_create(name="DIRECTORA")

            grupo.permissions.set(permisos)

            directoras = Usuario.objects.filter(
                rol="DIRECTORA",
                estado_cuenta="ACTIVA",
            )

            for directora in directoras:
                if not directora.is_staff:
                    directora.is_staff = True
                    directora.save(update_fields=["is_staff"])

                directora.groups.add(grupo)

        except ProgrammingError as error:
            raise CommandError(
                "No existen las tablas de permisos del usuario. "
                "Ejecute primero el script "
                "24_permisos_usuario_django.sql."
            ) from error

        accion = "creado" if creado else "actualizado"

        self.stdout.write(
            self.style.SUCCESS(f"Grupo DIRECTORA {accion} correctamente.")
        )

        self.stdout.write(
            self.style.SUCCESS(f"Permisos asignados: {permisos.count()}.")
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Directoras activas configuradas: {directoras.count()}."
            )
        )
