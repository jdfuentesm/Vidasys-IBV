"""Cancelaciones institucionales en SQLite efímero; sin acceso a PostgreSQL."""
import importlib
import uuid
from datetime import date, time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection
from django.test import TestCase, Client
from django.urls import reverse

from .models import SolicitudAcademica, SesionClase, Curso
from .solicitudes import solicitar, decidir


class SolicitudesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_flujo import FlujoAcademicoTests
        FlujoAcademicoTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.curso = self.cursos[0]
        self.sesion = SesionClase.objects.create(curso=self.curso, numero_clase=1,
            fecha=date(2026, 2, 1), hora_inicio=time(8), hora_fin=time(9), estado='PROGRAMADA')
        self.clave = uuid.uuid4()

    def solicitar(self, **kwargs):
        return solicitar(**(dict(sesion_id=self.sesion.pk, usuario=self.docente,
                                 motivo='Cambio institucional', clave=self.clave) | kwargs))

    def decidir(self, solicitud, **kwargs):
        return decidir(**(dict(solicitud_id=solicitud.pk, usuario=self.directora,
                               decision='APROBADA') | kwargs))

    def test_solicitud_no_cambia_sesion_e_idempotencia(self):
        s = self.solicitar()
        self.assertEqual(self.solicitar().pk, s.pk)
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, 'PROGRAMADA')
        self.assertEqual(s.anteriores['sesion']['estado'], 'PROGRAMADA')
        with self.assertRaises(ValidationError): self.solicitar(motivo='Otro motivo')
        with self.assertRaises(ValidationError): self.solicitar(clave=uuid.uuid4())

    def test_aprobar_y_reintentar_conserva_auditoria(self):
        s = self.solicitar()
        res = self.decidir(s)
        fecha = res.fecha_decision
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, 'CANCELADA')
        self.assertEqual(res.directora_id, self.directora.pk)
        self.assertEqual(res.aplicados['sesion']['estado'], 'CANCELADA')
        self.assertEqual(self.decidir(s).fecha_decision, fecha)
        with self.assertRaises(ValidationError): self.decidir(s, decision='RECHAZADA', motivo='Cambio')
        self.curso.refresh_from_db()
        self.assertEqual(self.curso.estado, 'ACTIVO')

    def test_rechazar_exige_motivo_y_no_cambia_sesion(self):
        s = self.solicitar()
        with self.assertRaises(ValidationError): self.decidir(s, decision='RECHAZADA')
        res = self.decidir(s, decision='RECHAZADA', motivo='Debe reprogramarse')
        self.assertEqual(res.estado, 'RECHAZADA')
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, 'PROGRAMADA')
        self.assertEqual(res.aplicados, {})

    def test_roles_no_reciben_autoridad_por_ser_superusuario(self):
        s = self.solicitar()
        for rol in ('ADMINISTRADOR', 'MAESTRO', 'SECRETARIA', 'ESTUDIANTE', 'PASTOR_PRINCIPAL'):
            self.directora.rol = rol
            self.directora.is_superuser = True
            self.directora.save()
            with self.assertRaises(ValidationError): self.decidir(s)
        s.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')

    def test_docente_ajeno_y_motivo_vacio(self):
        with self.assertRaises(ValidationError): self.solicitar(usuario=self.directora)
        with self.assertRaises(ValidationError): self.solicitar(motivo='  ')
        from .models import Maestro
        otro = Maestro.objects.create(usuario=self.directora, nombres="Otra", apellidos="Persona", pais="SV", estado="ACTIVO")
        self.curso.maestro = otro
        self.curso.save()
        with self.assertRaises(ValidationError): self.solicitar()

    def test_estados_no_permitidos_y_suspendida(self):
        for estado in ('IMPARTIDA', 'CANCELADA'):
            SesionClase.objects.filter(pk=self.sesion.pk).update(estado=estado)
            with self.assertRaises(ValidationError): self.solicitar()
        SesionClase.objects.filter(pk=self.sesion.pk).update(estado='SUSPENDIDA')
        self.decidir(self.solicitar())
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, 'CANCELADA')

    def test_curso_finalizado_o_cancelado_no_admite_solicitudes(self):
        for estado in ('FINALIZADO', 'CANCELADO'):
            Curso.objects.filter(pk=self.curso.pk).update(estado=estado)
            with self.assertRaises(ValidationError): self.solicitar()

    def test_solicitud_obsoleta_no_sobrescribe_y_puede_rechazarse(self):
        s = self.solicitar()
        SesionClase.objects.filter(pk=self.sesion.pk).update(hora_fin=time(10))
        with self.assertRaisesMessage(ValidationError, 'obsoleta'): self.decidir(s)
        s.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')
        self.decidir(s, decision='RECHAZADA', motivo='Datos cambiaron')

    def test_asistencia_impide_solicitud_y_aprobacion(self):
        from .flujo import matricular
        from .models import Asistencia
        _, inscripciones, _ = matricular(estudiante=self.estudiante, ciclo=self.ciclo,
            numero_matricula='SOL-1', fecha_matricula=date(2026, 1, 2))
        s = self.solicitar()
        Asistencia.objects.create(inscripcion=inscripciones[0], sesion=self.sesion, estado_asistencia='PRESENTE')
        with self.assertRaises(ValidationError): self.decidir(s)
        self.decidir(s, decision='RECHAZADA', motivo='La sesión ya tiene asistencia')
        with self.assertRaises(ValidationError): self.solicitar(clave=uuid.uuid4())

    def test_cambio_de_curso_o_docente_bloquea_aprobacion(self):
        s = self.solicitar()
        Curso.objects.filter(pk=self.curso.pk).update(estado='FINALIZADO')
        with self.assertRaises(ValidationError): self.decidir(s)

    def test_rollback_si_falla_guardado_de_decision(self):
        s = self.solicitar()
        with patch.object(SolicitudAcademica, 'save', side_effect=DatabaseError('fallo simulado')):
            with self.assertRaises(DatabaseError): self.decidir(s)
        self.sesion.refresh_from_db(); s.refresh_from_db()
        self.assertEqual(self.sesion.estado, 'PROGRAMADA')
        self.assertEqual(s.estado, 'PENDIENTE')
        self.assertIsNone(s.directora_id)

    def test_web_flujo_completo_y_permisos(self):
        self.client.force_login(self.docente)
        url = reverse('solicitar_cancelacion', args=[self.sesion.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {'clave': self.clave, 'motivo': 'Cambio'}).status_code, 302)
        s = SolicitudAcademica.objects.get()
        detalle = reverse('solicitud_academica', args=[s.pk])
        self.assertEqual(self.client.post(detalle, {'decision': 'APROBADA'}).status_code, 403)
        self.client.force_login(self.directora)
        self.assertContains(self.client.get(reverse('solicitudes_academicas')), 'Pendientes')
        self.assertContains(self.client.post(detalle, {'decision': 'RECHAZADA'}), 'Indique el motivo')
        self.assertEqual(self.client.post(detalle, {'decision': 'APROBADA'}).status_code, 302)
        self.assertContains(self.client.get(detalle), 'Aprobada')

    def test_csrf_y_acceso_anonimo(self):
        url = reverse('solicitar_cancelacion', args=[self.sesion.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.docente)
        self.assertEqual(client.post(url, {'clave': self.clave, 'motivo':'Cambio'}).status_code, 403)

    def test_migracion_solo_crea_tabla_nueva(self):
        migration = importlib.import_module('academico.migrations.0001_initial').Migration
        from django.db.migrations.operations.special import SeparateDatabaseAndState
        from django.db.migrations.operations.models import CreateModel
        self.assertEqual(len(migration.operations), 2)
        estado, nueva = migration.operations
        self.assertIsInstance(estado, SeparateDatabaseAndState)
        self.assertEqual(estado.database_operations, [])
        self.assertTrue(all(op.options.get('managed') is False for op in estado.state_operations))
        self.assertIsInstance(nueva, CreateModel)
        self.assertEqual(nueva.name, 'SolicitudAcademica')
        self.assertIn('solicitud_academica', connection.introspection.table_names())

    def test_historial_inmutable_y_solicitud_no_editable(self):
        s = self.solicitar()
        s.motivo = 'Sustituir motivo'
        with self.assertRaises(ValidationError): s.save()
        s.refresh_from_db()
        s = self.decidir(s)
        s.motivo_decision = 'Alterar resolución'
        with self.assertRaises(ValidationError): s.save()
        with self.assertRaises(ValidationError): s.delete()

    def test_cuenta_inactiva_no_solicita_ni_decide(self):
        s = self.solicitar()
        self.directora.estado_cuenta = 'BLOQUEADA'
        self.directora.save()
        with self.assertRaises(ValidationError): self.decidir(s)
        self.docente.estado_cuenta = 'INACTIVA'
        self.docente.save()
        with self.assertRaises(ValidationError): self.solicitar(clave=uuid.uuid4())

    def test_web_curso_ajeno_y_admin_sin_acceso(self):
        self.client.force_login(self.docente)
        s = self.solicitar()
        from .models import Maestro
        otro = Maestro.objects.create(usuario=self.directora, nombres='Otra', apellidos='Persona', pais='SV', estado='ACTIVO')
        Curso.objects.filter(pk=self.curso.pk).update(maestro=otro)
        self.assertEqual(self.client.get(reverse('solicitar_cancelacion', args=[self.sesion.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('solicitud_academica', args=[s.pk])).status_code, 404)
        self.directora.rol = 'ADMINISTRADOR'
        self.directora.is_superuser = True
        self.directora.save()
        self.client.force_login(self.directora)
        self.assertEqual(self.client.get(reverse('solicitudes_academicas')).status_code, 403)

    def test_extraordinaria_conserva_autorizacion_original(self):
        from django.utils import timezone
        sesion = SesionClase.objects.create(curso=self.curso, numero_clase=7, fecha=date(2026, 3, 1),
            hora_inicio=time(8), hora_fin=time(9), estado='PROGRAMADA', motivo_extension='Reposición',
            usuario_autoriza=self.directora, fecha_autorizacion=timezone.now())
        fecha = sesion.fecha_autorizacion
        s = self.solicitar(sesion_id=sesion.pk)
        self.decidir(s)
        sesion.refresh_from_db()
        self.assertEqual(sesion.fecha_autorizacion, fecha)
        self.assertEqual(sesion.usuario_autoriza_id, self.directora.pk)
        self.assertEqual(sesion.motivo_extension, 'Reposición')

    def test_cancelacion_permite_cierre_valido_y_conserva_formula(self):
        from decimal import Decimal
        from .models import Asistencia, Calificacion
        from .flujo import matricular, requisitos_cierre, cerrar_curso, firma_cierre
        SesionClase.objects.filter(pk=self.sesion.pk).update(numero_clase=6)
        _, inscripciones, _ = matricular(estudiante=self.estudiante, ciclo=self.ciclo,
            numero_matricula='CIERRE-SOL', fecha_matricula=date(2026, 1, 2))
        inscripcion = inscripciones[0]
        for n in range(1, 6):
            sesion = SesionClase.objects.create(curso=self.curso, numero_clase=n,
                fecha=date(2026, 2, n), hora_inicio=time(8), hora_fin=time(9), estado='IMPARTIDA')
            Asistencia.objects.create(sesion=sesion, inscripcion=inscripcion, estado_asistencia='PRESENTE')
        nota = Calificacion.objects.create(inscripcion=inscripcion, nota_asistencia=Decimal('40'),
            nota_uniforme=Decimal('20'), nota_participacion=Decimal('20'), nota_companerismo=Decimal('20'),
            tarea_1=Decimal('62.5'), examen_1=Decimal('62.5'), tarea_2=Decimal('62.5'), examen_2=Decimal('62.5'))
        self.assertTrue(requisitos_cierre(self.curso))
        self.decidir(self.solicitar())
        nota.refresh_from_db()
        self.assertEqual(nota.estado, 'PENDIENTE')
        self.assertEqual(nota.nota_final, Decimal('70'))
        self.assertEqual(requisitos_cierre(self.curso), [])
        revision = firma_cierre(self.curso, list(SesionClase.objects.filter(curso=self.curso).order_by('numero_clase')))
        cerrar_curso(self.curso.pk, self.docente, revision)
        nota.refresh_from_db(); inscripcion.refresh_from_db()
        self.assertEqual(nota.estado, 'APROBADA')
        self.assertEqual(inscripcion.estado, 'APROBADA')

    def test_cancelacion_no_elude_minimo_de_cinco_impartidas(self):
        from .flujo import requisitos_cierre
        self.decidir(self.solicitar())
        self.assertTrue(any('5 clases' in error for error in requisitos_cierre(self.curso)))

    def test_motivo_se_escapa_y_decision_exige_csrf(self):
        s = self.solicitar(motivo='<script>alert(1)</script>')
        self.client.force_login(self.directora)
        url = reverse('solicitud_academica', args=[s.pk])
        response = self.client.get(url)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.directora)
        self.assertEqual(client.post(url, {'decision':'APROBADA'}).status_code, 403)

    def test_reasignacion_docente_posterior_conserva_solicitud(self):
        from .models import Maestro
        s = self.solicitar()
        otro = Maestro.objects.create(usuario=self.directora, nombres='Otra', apellidos='Docente', pais='SV', estado='ACTIVO')
        Curso.objects.filter(pk=self.curso.pk).update(maestro=otro)
        with self.assertRaises(ValidationError): self.decidir(s)
        s.refresh_from_db(); self.sesion.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')
        self.assertEqual(self.sesion.estado, 'PROGRAMADA')
        self.decidir(s, decision='RECHAZADA', motivo='Reasignación docente')

    def test_cambios_fechas_curso_invalidan_incluso_si_sesion_sigue_dentro(self):
        for cambio in ({'fecha_inicio':date(2026,1,3)}, {'fecha_fin':date(2026,11,30)}):
            with self.subTest(cambio=cambio):
                s = self.solicitar(clave=uuid.uuid4())
                Curso.objects.filter(pk=self.curso.pk).update(**cambio)
                with self.assertRaisesMessage(ValidationError, 'obsoleta'): self.decidir(s)
                self.decidir(s, decision='RECHAZADA', motivo='Cambio de fechas')
                Curso.objects.filter(pk=self.curso.pk).update(fecha_inicio=date(2026,1,1),fecha_fin=date(2026,12,31))

    def test_fecha_y_estado_sesion_obsoletos(self):
        for cambio in ({'fecha':date(2026,2,2)}, {'estado':'SUSPENDIDA'}, {'estado':'IMPARTIDA'}):
            with self.subTest(cambio=cambio):
                s = self.solicitar(clave=uuid.uuid4())
                SesionClase.objects.filter(pk=self.sesion.pk).update(**cambio)
                with self.assertRaisesMessage(ValidationError, 'obsoleta'): self.decidir(s)
                s.refresh_from_db()
                self.assertEqual(s.estado, 'PENDIENTE')
                self.decidir(s, decision='RECHAZADA', motivo='Cambió la sesión')
                SesionClase.objects.filter(pk=self.sesion.pk).update(fecha=date(2026,2,1),estado='PROGRAMADA')

    def test_cambio_rol_solicitante_y_directora_usa_datos_actuales(self):
        s = self.solicitar()
        self.docente.rol = 'SECRETARIA'
        self.docente.save()
        with self.assertRaises(ValidationError): self.decidir(s)
        self.docente.rol = 'MAESTRO'
        self.docente.save()
        self.directora.rol = 'ADMINISTRADOR'
        self.directora.is_superuser = True
        self.directora.save()
        with self.assertRaises(ValidationError): self.decidir(s)
        s.refresh_from_db(); self.sesion.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')
        self.assertEqual(self.sesion.estado, 'PROGRAMADA')

    def test_periodo_invalido_y_sesion_fuera_de_curso_no_se_solicitan(self):
        Curso.objects.filter(pk=self.curso.pk).update(fecha_inicio=date(2026,2,2))
        with self.assertRaisesMessage(ValidationError, 'período'): self.solicitar()
        Curso.objects.filter(pk=self.curso.pk).update(fecha_inicio=date(2026,12,31),fecha_fin=date(2026,1,1))
        with self.assertRaises(ValidationError): self.solicitar()

    def test_ui_oculta_accion_y_ruta_directa_para_sesion_no_valida(self):
        self.client.force_login(self.docente)
        SesionClase.objects.filter(pk=self.sesion.pk).update(estado='IMPARTIDA')
        url = reverse('solicitar_cancelacion', args=[self.sesion.pk])
        response = self.client.get(url)
        self.assertContains(response, 'No puede solicitar cancelación')
        self.assertNotContains(response, 'Enviar a Dirección')
        gestion = self.client.get(reverse('gestionar_sesion', args=[self.curso.pk,self.sesion.pk]))
        self.assertNotContains(gestion, 'Solicitar cancelación a Dirección')
        self.assertContains(gestion, 'No puede solicitar cancelación')
        self.client.post(url, {'clave':self.clave,'motivo':'Intento directo'})
        self.assertFalse(SolicitudAcademica.objects.exists())

    def test_ui_no_ofrece_cancelar_con_asistencia(self):
        from .flujo import matricular
        from .models import Asistencia
        _, inscripciones, _ = matricular(estudiante=self.estudiante,ciclo=self.ciclo,
            numero_matricula='AS-UI',fecha_matricula=date(2026,1,2))
        Asistencia.objects.create(inscripcion=inscripciones[0],sesion=self.sesion,estado_asistencia='PRESENTE')
        self.client.force_login(self.docente)
        for url in (reverse('solicitar_cancelacion',args=[self.sesion.pk]),reverse('gestionar_sesion',args=[self.curso.pk,self.sesion.pk])):
            response=self.client.get(url)
            self.assertContains(response, 'asistencia registrada')
            self.assertNotContains(response, 'Enviar a Dirección')
            self.assertNotContains(response, 'Solicitar cancelación a Dirección')

    def test_base_impide_pendientes_duplicadas_y_rechazos_sin_motivo(self):
        from django.db import IntegrityError, transaction
        s = self.solicitar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SolicitudAcademica.objects.create(clave=uuid.uuid4(),curso=self.curso,sesion=self.sesion,
                solicitante=self.docente,motivo='Duplicada',anteriores=s.anteriores)
        for motivo in ('', '  ', '\t\n'):
            with self.subTest(motivo=motivo), self.assertRaises(IntegrityError), transaction.atomic():
                SolicitudAcademica.objects.filter(pk=s.pk).update(estado='RECHAZADA',directora=self.directora,
                    fecha_decision=s.fecha_solicitud,motivo_decision=motivo)
        s.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')

    def test_orden_bloqueos_compartido_con_extraordinarias(self):
        from django.db.models.query import QuerySet
        from .flujo import autorizar_extra
        from django.utils import timezone
        original = QuerySet.select_for_update
        orden=[]
        def registrar(qs,*args,**kwargs):
            orden.append(qs.model.__name__)
            return original(qs,*args,**kwargs)
        with patch.object(QuerySet, 'select_for_update', registrar):
            s=self.solicitar()
        self.assertEqual(orden[:4],['Usuario','Curso','Maestro','SesionClase'])
        orden.clear()
        with patch.object(QuerySet, 'select_for_update', registrar):
            self.decidir(s)
        self.assertEqual(orden,['Usuario','Curso','Maestro','SesionClase','SolicitudAcademica'])
        orden.clear()
        sesion=SesionClase(curso=self.curso,numero_clase=7,fecha=date(2026,3,1),hora_inicio=time(8),hora_fin=time(9),
            estado='PROGRAMADA',motivo_extension='Extra',usuario_autoriza=self.directora,fecha_autorizacion=timezone.now())
        with patch.object(QuerySet, 'select_for_update', registrar):
            autorizar_extra(sesion,self.directora)
        self.assertEqual(orden[:2],['Usuario','Curso'])

    def test_permisos_se_reconsultan_aunque_objeto_del_actor_este_desactualizado(self):
        from core.models import Usuario
        s=self.solicitar()
        Usuario.objects.filter(pk=self.docente.pk).update(estado_cuenta='BLOQUEADA')
        self.assertTrue(self.docente.is_active)
        with self.assertRaises(ValidationError): self.decidir(s)
        Usuario.objects.filter(pk=self.docente.pk).update(estado_cuenta='ACTIVA')
        Usuario.objects.filter(pk=self.directora.pk).update(rol='SECRETARIA')
        self.assertEqual(self.directora.rol,'DIRECTORA')
        with self.assertRaises(ValidationError): self.decidir(s)
        s.refresh_from_db()
        self.assertEqual(s.estado,'PENDIENTE')
