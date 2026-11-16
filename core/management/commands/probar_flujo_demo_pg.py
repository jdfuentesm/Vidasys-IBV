"""Ensayo integrado, sintético y siempre revertido; nunca instala el esquema."""
import secrets
from datetime import date, time, timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.test import Client, override_settings
from django.test.utils import setup_test_environment, teardown_test_environment
from django.urls import reverse
from django.utils import timezone

from core.demo_preflight import verificar_esquema_demo


class Command(BaseCommand):
    help = 'Probar el flujo integrado SOLO en Neon demo; siempre revierte los registros.'
    # Evita comprobaciones automáticas anteriores a las defensas de destino.
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true')

    def exigir(self, condicion, mensaje):
        if not condicion:
            raise CommandError(mensaje)

    def handle(self, *args, **options):
        self.exigir(options['confirmar'], 'Requiere --confirmar; avanza secuencias aunque revierta los registros.')
        self.exigir(settings.SETTINGS_MODULE == 'config.settings_demo_pg', 'Use config.settings_demo_pg.')
        self.exigir(connection.vendor == 'postgresql', 'Requiere PostgreSQL.')
        self.exigir(connection.settings_dict['NAME'] == 'vidasys_demo'
                    and connection.settings_dict['USER'] == 'vidasys_demo_limitado', 'Destino no autorizado.')
        self.exigir(set(settings.DATABASES) == {'default'} and not settings.DATABASE_ROUTERS,
                    'El ensayo exige una única conexión default y ningún router.')
        self.exigir(settings.FINANCIERO_CALENDARIO_BACKEND == 'postgresql', 'El calendario debe ser transaccional en PostgreSQL.')
        self.exigir(not connection.in_atomic_block and connection.get_autocommit(),
                    'Ejecute como comando independiente, fuera de otra transacción.')
        modelos = [m for m in apps.get_models() if m._meta.app_label in ('core', 'academico', 'financiero')
                   and not m._meta.proxy]
        with transaction.atomic():
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT current_database(), current_user')
                    self.exigir(cursor.fetchone() == ('vidasys_demo', 'vidasys_demo_limitado'),
                                'La conexión efectiva no coincide con el destino demo.')
                    cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = %s)", ['gestion_ibv'])
                    self.exigir(not cursor.fetchone()[0], 'El servidor contiene la base institucional; se rechaza el ensayo.')
                    cursor.execute('SET LOCAL search_path TO public')
                    cursor.execute("SET LOCAL lock_timeout = '5s'")
                    cursor.execute("SET LOCAL statement_timeout = '30s'")
                    # Comparte bloqueo con el sembrador; no se ejecuta aquel comando.
                    cursor.execute('SELECT pg_advisory_xact_lock(%s)', [739185294])
                    cursor.execute('SELECT CURRENT_DATE')
                    self.exigir(cursor.fetchone()[0] == timezone.localdate(), 'Fechas Django/PostgreSQL distintas; revisar zona horaria.')
                verificar_esquema_demo()
                self.exigir(not any(m.objects.exists() for m in modelos),
                            'Hay datos de aplicación. Use una demo sin datos; no se modifica información existente.')
                self.ejecutar_flujo()
                # Fuerza también la validación de FK diferidas antes de revertir.
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            finally:
                # Sin opción para conservar datos, incluso si una comprobación falla.
                transaction.set_rollback(True)
        self.exigir(not any(m.objects.exists() for m in modelos), 'Se detectaron datos después de la reversión; revisar uso concurrente.')
        self.stdout.write(self.style.SUCCESS('Flujo integrado correcto y registros revertidos. Las secuencias pueden haber avanzado.'))

    def ejecutar_flujo(self):
        from academico.flujo import matricular
        from academico.models import (Asistencia, Calificacion, CicloAcademico, Curso,
                                      Estudiante, Maestro, Materia, SesionClase)
        from core.models import Usuario
        from financiero.calendario import guardar, leer
        from financiero.consultas import cuenta, importes, solvente
        from financiero.models import ConceptoCobro, ConvenioPago, ConvenioObligacion, CuotaConvenio, Pago
        from financiero.servicios import registrar_pago, reservar_recibo

        hoy = timezone.localdate()
        inicio, fin = date(hoy.year, 1, 1), date(hoy.year, 12, 31)
        prefijo = 'ens-' + secrets.token_hex(4)
        clave = secrets.token_urlsafe(32)  # Solo memoria; nunca se imprime ni escribe en archivos.
        usuarios = {}
        for rol in ('SECRETARIA', 'DIRECTORA', 'MAESTRO', 'ESTUDIANTE'):
            numero = f'{prefijo}-{rol.lower()}'
            usuarios[rol] = Usuario.objects.create_user(numero, numero + '@example.test', clave,
                                                       rol=rol, debe_cambiar_password=False)
        maestro = Maestro.objects.create(usuario=usuarios['MAESTRO'], nombres='Docente sintético',
                                          apellidos='Ensayo', pais='SV', estado='ACTIVO')
        alumno = Estudiante.objects.create(usuario=usuarios['ESTUDIANTE'], codigo_estudiante=prefijo + '-e',
                                           nombres='Estudiante sintético', apellidos='Ensayo', fecha_ingreso=inicio, estado='ACTIVO')
        ajeno_usuario = Usuario.objects.create_user(prefijo + '-ajeno', prefijo + '-ajeno@example.test', clave, rol='ESTUDIANTE')
        ajeno = Estudiante.objects.create(usuario=ajeno_usuario, codigo_estudiante=prefijo + '-privado',
                                          nombres='Otro sintético', apellidos='Ensayo', fecha_ingreso=inicio, estado='ACTIVO')
        ciclo = CicloAcademico.objects.create(nombre='Ciclo sintético de ensayo', numero_ciclo=1, anio=hoy.year,
                                              fecha_inicio=inicio, fecha_fin=fin, estado='ACTIVO')
        conceptos = [ConceptoCobro.objects.create(nombre=n, estado='ACTIVO', permite_abonos=False)
                     for n in ('MATRICULA', 'MENSUALIDAD')]
        calendario = {'emision': str(inicio), 'matricula': str(inicio),
                      'meses': [f'{hoy.year}-{mes:02}' for mes in range(2, 7)],
                      'concepto_matricula': conceptos[0].pk, 'concepto_mensualidad': conceptos[1].pk}
        guardar(ciclo, calendario)
        self.exigir(leer(ciclo)['meses'] == calendario['meses'], 'Calendario compartido no persistido.')
        for n in range(1, 7):
            materia = Materia.objects.create(codigo_materia=f'{prefijo}-m{n}', nombre=f'Materia sintética {n}',
                                             numero_ciclo_formativo=1, estado='ACTIVA')
            Curso.objects.create(materia=materia, maestro=maestro, ciclo=ciclo, fecha_inicio=inicio,
                                 fecha_fin=fin, modalidad='PRESENCIAL', estado='ACTIVO')
        argumentos = dict(estudiante=alumno, ciclo=ciclo, numero_matricula=prefijo + '-mat', fecha_matricula=inicio)
        matricula, inscripciones, creada = matricular(**argumentos)
        self.exigir(creada and len(inscripciones) == 6, 'La matrícula no generó seis inscripciones.')
        obligaciones = list(matricula.obligaciones.order_by('pk'))
        self.exigir(len(obligaciones) == 6, 'La matrícula no generó seis obligaciones.')
        self.exigir(not matricular(**argumentos)[2] and matricula.obligaciones.count() == 6,
                    'La repetición duplicó la matrícula u obligaciones.')
        saldo_inicial = cuenta(alumno)['saldo_total']
        # Vence únicamente NUESTRA obligación de matrícula; preserva la unicidad de las mensualidades.
        matricula.obligaciones.filter(pk=obligaciones[0].pk).update(fecha_vencimiento=hoy - timedelta(days=1))
        self.exigir(not solvente(alumno), 'La función SQL no detecta insolvencia.')
        self.verificar_vistas(alumno, False, saldo_inicial)
        with self.entorno_http():
            cliente = Client()
            self.exigir(cliente.login(username=usuarios['ESTUDIANTE'].numero_usuario, password=clave), 'Falló autenticación Django.')
            self.peticion(cliente, 'portal_academico', 403)
            self.peticion(cliente, 'portal_cuenta', 200)
            # Excepción institucional: convenio sintético activo para todas las obligaciones vencidas.
            convenio = ConvenioPago.objects.create(estudiante=alumno, usuario_autoriza=usuarios['DIRECTORA'],
                fecha_convenio=hoy, monto_convenido=saldo_inicial, numero_cuotas=1, estado='ACTIVO')
            for obligacion in obligaciones:
                ConvenioObligacion.objects.create(convenio=convenio, obligacion=obligacion,
                                                  saldo_incluido=importes(obligacion)[2])
            cuota = CuotaConvenio.objects.create(convenio=convenio, numero_cuota=1,
                fecha_vencimiento=hoy + timedelta(days=1), monto_cuota=saldo_inicial, estado='PENDIENTE')
            self.exigir(solvente(alumno), 'El SQL no respeta la excepción de convenio vigente.')
            self.verificar_vistas(alumno, True, saldo_inicial)
            self.peticion(cliente, 'portal_academico', 200)
            convenio.estado = 'INCUMPLIDO'
            convenio.save(update_fields=['estado'])
            self.exigir(not solvente(alumno), 'El convenio incumplido permite solvencia.')
            # Descarta exclusivamente este escenario de convenio, conservando el resto del ensayo.
            ConvenioObligacion.objects.filter(convenio=convenio).delete()
            cuota.delete()
            convenio.delete()
            token = reservar_recibo(usuarios['SECRETARIA'], alumno)
            aplicaciones = [(o.pk, importes(o)[2]) for o in obligaciones]
            datos_pago = dict(usuario=usuarios['SECRETARIA'], estudiante=alumno, token=token,
                              metodo='EFECTIVO', referencia=prefijo, aplicaciones=aplicaciones)
            pago, creado = registrar_pago(**datos_pago)
            self.exigir(creado and pago.monto_total == saldo_inicial, 'El pago no coincide con el saldo generado.')
            repetido, creado = registrar_pago(**datos_pago)
            self.exigir(not creado and repetido.pk == pago.pk and Pago.objects.count() == 1, 'Se duplicó el pago.')
            self.exigir(cuenta(alumno)['saldo_total'] == Decimal('0') and solvente(alumno), 'El pago no regularizó la cuenta.')
            self.verificar_vistas(alumno, True, Decimal('0'))
            self.exigir(set(matricula.obligaciones.values_list('estado', flat=True)) == {'PAGADA'},
                        'El recálculo SQL no marcó las obligaciones pagadas.')
            pago.estado = 'ANULADO'
            pago.save(update_fields=['estado'])
            self.exigir(cuenta(alumno)['saldo_total'] == saldo_inicial and not solvente(alumno),
                        'Un pago anulado sigue computando como ingreso.')
            self.exigir('PAGADA' not in matricula.obligaciones.values_list('estado', flat=True),
                        'El trigger no recalculó las obligaciones tras anular el pago sintético.')
            pago.estado = 'REGISTRADO'
            pago.save(update_fields=['estado'])
            self.verificar_vistas(alumno, True, Decimal('0'))
            sesion = SesionClase.objects.create(curso=inscripciones[0].curso, numero_clase=1, fecha=hoy,
                                                hora_inicio=time(8), hora_fin=time(9), estado='IMPARTIDA')
            cliente.force_login(usuarios['MAESTRO'])
            parametros = {'curso': sesion.curso_id, 'sesion': sesion.pk}
            respuesta = self.peticion(cliente, 'registrar_asistencia', 200, datos=parametros)
            filas = respuesta.context['filas']
            self.exigir(len(filas) == 1, 'Listado de asistencia inesperado.')
            pk = inscripciones[0].pk
            self.peticion(cliente, 'registrar_asistencia', 302, metodo='post', datos=dict(parametros,
                inscripciones=[str(pk)], **{f'asistencia-{pk}-revision': filas[0]['form'].initial['revision'],
                                          f'asistencia-{pk}-estado_asistencia': 'PRESENTE'}))
            self.exigir(Asistencia.objects.filter(inscripcion_id=pk, sesion=sesion, estado_asistencia='PRESENTE').exists(),
                        'La vista no guardó asistencia.')
            respuesta = self.peticion(cliente, 'registrar_calificacion', 200, datos={'curso': sesion.curso_id})
            datos = {'curso': sesion.curso_id, 'inscripciones': [str(pk)], 'accion': 'guardar',
                     f'nota-{pk}-revision': respuesta.context['filas'][0]['form'].initial['revision']}
            datos.update({f'nota-{pk}-{campo}': str(valor) for campo, valor in
                          zip(Calificacion.COMPONENTES, [40, 20, 20, 20, 0, 80, 80, 80, 80])})
            self.peticion(cliente, 'registrar_calificacion', 302, metodo='post', datos=datos)
            nota = Calificacion.objects.get(inscripcion_id=pk)
            self.exigir(nota.nota_final == nota.calcular_nota() and nota.estado == 'APROBADA', 'Calificación integrada incorrecta.')
            self.verificar_permisos(usuarios, alumno, ajeno, ajeno_usuario, pago, sesion.curso_id)
        self.stdout.write('Matrícula, obligaciones, pago idempotente, asistencia, notas, solvencia, vistas y permisos: correctos.')

    def verificar_vistas(self, alumno, solvente_esperado, saldo):
        with connection.cursor() as cursor:
            cursor.execute('SELECT puede_consultar_academico FROM vw_acceso_portal_estudiante WHERE id_estudiante=%s', [alumno.pk])
            self.exigir(cursor.fetchone() == (solvente_esperado,), 'Vista de acceso incompatible con solvencia.')
            cursor.execute('SELECT count(*), sum(saldo_pendiente) FROM vw_estado_cuenta_estudiante WHERE id_estudiante=%s', [alumno.pk])
            self.exigir(cursor.fetchone() == (6, saldo), 'Vista de estado de cuenta incorrecta.')
            cursor.execute('SELECT total_obligaciones, saldo_pendiente FROM vw_resumen_cuenta_estudiante WHERE id_estudiante=%s', [alumno.pk])
            self.exigir(cursor.fetchone() == (6, saldo), 'Vista de resumen incorrecta.')

    def entorno_http(self):
        from contextlib import contextmanager

        @contextmanager
        def entorno():
            # Peticiones internas: sin servidor, correo, red ni collectstatic.
            with override_settings(ALLOWED_HOSTS=['testserver'], EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
                setup_test_environment(debug=False)
                try:
                    yield
                finally:
                    teardown_test_environment()
        return entorno()

    def peticion(self, cliente, nombre, esperado, *, args=None, datos=None, metodo='get'):
        respuesta = getattr(cliente, metodo)(reverse(nombre, args=args), datos or {}, secure=True)
        self.exigir(respuesta.status_code == esperado,
                    f'{nombre}: HTTP {respuesta.status_code}; se esperaba {esperado}.')
        return respuesta

    def verificar_permisos(self, usuarios, alumno, ajeno, ajeno_usuario, pago, curso_id):
        matriz = {
            'estudiantes': {'SECRETARIA', 'DIRECTORA'},
            'matricula_secretaria': {'SECRETARIA', 'DIRECTORA'},
            'autorizar_clase_extraordinaria': {'DIRECTORA'},
            'registrar_calificacion': {'MAESTRO'},
            'registrar_asistencia': {'MAESTRO'},
            'mis_cursos': {'MAESTRO'},
            'finanzas_panel': {'SECRETARIA', 'DIRECTORA'},
            'finanzas_calendario': {'SECRETARIA'},
            'portal_academico': {'ESTUDIANTE'},
            'portal_cuenta': {'ESTUDIANTE'},
            'usuarios': set(),
        }
        cliente = Client()
        for rol, usuario in usuarios.items():
            cliente.force_login(usuario)
            for nombre, autorizados in matriz.items():
                self.peticion(cliente, nombre, 200 if rol in autorizados else 403)
                if rol not in autorizados:
                    self.peticion(cliente, nombre, 405 if nombre in ('portal_academico', 'portal_cuenta') else 403, metodo='post')
        cliente.force_login(usuarios['ESTUDIANTE'])
        for nombre in ('portal_inicio', 'portal_academico', 'portal_cuenta'):
            respuesta = self.peticion(cliente, nombre, 200, datos={'estudiante': ajeno.pk, 'usuario': ajeno_usuario.pk})
            self.exigir(ajeno.codigo_estudiante not in respuesta.content.decode(), 'El portal expuso el expediente ajeno.')
        self.peticion(cliente, 'portal_recibo', 200, args=[pago.pk])
        self.peticion(cliente, 'portal_cuenta', 405, metodo='post')
        self.peticion(cliente, 'finanzas_cuenta', 403, args=[alumno.pk])
        cliente.force_login(ajeno_usuario)
        self.peticion(cliente, 'portal_recibo', 404, args=[pago.pk])
        self.peticion(cliente, 'registrar_asistencia', 403, datos={'curso': curso_id})
        # Un segundo maestro sintético sin cursos no puede entrar al del primero.
        from core.models import Usuario
        otro = Usuario.objects.create_user('ens-otro-' + secrets.token_hex(4), 'otro-' + secrets.token_hex(4) + '@example.test',
                                           secrets.token_urlsafe(32), rol='MAESTRO')
        cliente.force_login(otro)
        for nombre in ('registrar_asistencia', 'registrar_calificacion'):
            self.peticion(cliente, nombre, 404, datos={'curso': curso_id})
        anonimo = Client()
        self.peticion(anonimo, 'portal_cuenta', 302)
