"""Correcciones definitivas: datos ficticios, exclusivamente SQLite de pruebas."""
import importlib
import uuid
from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase, Client
from django.urls import reverse

from .models import (Asistencia, Calificacion, Curso, InscripcionCurso, Maestro,
                     Matricula, SesionClase, SolicitudAcademica)
from .correcciones import (firma_nota, propuesta_nota, solicitar_correccion,
                           validar_destino)
from .solicitudes import decidir


class CorreccionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_flujo import FlujoAcademicoTests
        FlujoAcademicoTests.setUpTestData.__func__(cls)

    def setUp(self):
        from .flujo import matricular, firma_cierre, cerrar_curso
        self.curso = self.cursos[0]
        _, inscripciones, _ = matricular(estudiante=self.estudiante, ciclo=self.ciclo,
            numero_matricula='CORR-1', fecha_matricula=date(2026,1,2))
        self.inscripcion = inscripciones[0]
        for n in range(1,6):
            sesion = SesionClase.objects.create(curso=self.curso,numero_clase=n,fecha=date(2026,2,n),
                hora_inicio=time(8),hora_fin=time(9),estado='IMPARTIDA')
            Asistencia.objects.create(inscripcion=self.inscripcion,sesion=sesion,estado_asistencia='PRESENTE')
        self.nota = Calificacion.objects.create(inscripcion=self.inscripcion,
            nota_asistencia=Decimal('40'),nota_uniforme=Decimal('20'),nota_participacion=Decimal('20'),
            nota_companerismo=Decimal('20'),tarea_1=Decimal('62.50'),examen_1=Decimal('62.50'),
            tarea_2=Decimal('62.50'),examen_2=Decimal('62.50'))
        cerrar_curso(self.curso.pk,self.docente,firma_cierre(self.curso,list(SesionClase.objects.filter(curso=self.curso).order_by('numero_clase'))))
        self.recargar()
        self.clave = uuid.uuid4()
        self.client.force_login(self.docente)

    def recargar(self):
        self.curso.refresh_from_db();self.inscripcion.refresh_from_db();self.nota.refresh_from_db()
        self.inscripcion.matricula.refresh_from_db()
        self.nota.inscripcion=self.inscripcion

    def componentes(self, **cambios):
        return {c:getattr(self.nota,c) for c in Calificacion.COMPONENTES}|{'tarea_1':Decimal('67.50')}|cambios

    def solicitar(self, **kwargs):
        return solicitar_correccion(**(dict(inscripcion_id=self.inscripcion.pk,usuario=self.docente,
            motivo='Corrección documentada',clave=self.clave,componentes=self.componentes(),
            revision=firma_nota(self.curso,self.inscripcion,self.nota))|kwargs))

    def aprobar(self, solicitud, **kwargs):
        return decidir(**(dict(solicitud_id=solicitud.pk,usuario=self.directora,decision='APROBADA')|kwargs))

    def test_solicitar_no_cambia_datos_y_aprobar_conserva_fechas_y_asistencia(self):
        antes_nota=Calificacion.objects.values().get(pk=self.nota.pk)
        antes_inscripcion=InscripcionCurso.objects.values().get(pk=self.inscripcion.pk)
        asistencia=list(Asistencia.objects.values())
        s=self.solicitar()
        self.assertEqual(Calificacion.objects.values().get(pk=self.nota.pk),antes_nota)
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.inscripcion.pk),antes_inscripcion)
        self.assertEqual(s.propuestos['nota_final'],'71.00')
        self.aprobar(s);self.recargar();s.refresh_from_db()
        self.assertEqual(self.nota.nota_final,Decimal('71'))
        self.assertEqual(self.curso.estado,'FINALIZADO')
        self.assertEqual(self.nota.fecha_registro,antes_nota['fecha_registro'])
        self.assertEqual(self.inscripcion.fecha_cierre,antes_inscripcion['fecha_cierre'])
        self.assertEqual(self.inscripcion.motivo_cierre,antes_inscripcion['motivo_cierre'])
        self.assertEqual(list(Asistencia.objects.values()),asistencia)
        self.assertEqual(s.anteriores['calificacion']['nota_final'],'70.00')
        self.assertEqual(s.aplicados['calificacion']['nota_final'],'71.00')
        self.assertEqual(s.directora_id,self.directora.pk)

    def test_frontera_6999_7000_cambia_resultado_en_ambos_sentidos(self):
        bajos={c:Decimal('62.49') for c in ['tarea_1','examen_1','tarea_2','examen_2']}
        s=self.solicitar(componentes=self.componentes(**bajos))
        self.aprobar(s);self.recargar()
        self.assertEqual(self.nota.nota_final,Decimal('69.99'))
        self.assertEqual(self.inscripcion.estado,'REPROBADA_ACADEMICAMENTE')
        altos={c:Decimal('62.50') for c in bajos}
        s=self.solicitar(clave=uuid.uuid4(),componentes=self.componentes(**altos))
        self.aprobar(s);self.recargar()
        self.assertEqual(self.nota.nota_final,Decimal('70.00'))
        self.assertEqual(self.inscripcion.estado,'APROBADA')

    def test_limites_decimales_y_campos_no_permitidos(self):
        for campo,limite in Calificacion.LIMITES_COMPONENTES.items():
            for valor in (Decimal('-0.01'),limite+Decimal('0.01'),None,'NaN','Infinity','1.001'):
                with self.subTest(campo=campo,valor=valor),self.assertRaises(ValidationError):
                    self.solicitar(componentes=self.componentes(**{campo:valor}))
        with self.assertRaises(ValidationError): self.solicitar(componentes=self.componentes()|{'nota_final':'100'})
        with self.assertRaises(ValidationError): self.solicitar(componentes={})
        self.assertFalse(SolicitudAcademica.objects.exists())

    def test_cero_maximos_y_extras_respetan_formula(self):
        cero={c:Decimal('0') for c in Calificacion.COMPONENTES}
        self.assertEqual(propuesta_nota(self.nota,cero)['nota_final'],'0.00')
        maximos=dict(Calificacion.LIMITES_COMPONENTES)
        self.assertEqual(propuesta_nota(self.nota,maximos)['nota_final'],'100.00')
        maximos['puntos_extras']=Decimal('0')
        self.assertEqual(propuesta_nota(self.nota,maximos)['nota_final'],'100.00')

    def test_duplicados_reintentos_y_decisiones_contradictorias(self):
        s=self.solicitar()
        self.assertEqual(self.solicitar().pk,s.pk)
        with self.assertRaises(ValidationError): self.solicitar(clave=uuid.uuid4())
        with self.assertRaises(ValidationError): self.solicitar(motivo='Otro motivo')
        self.aprobar(s);s.refresh_from_db();fecha=s.fecha_decision
        self.assertEqual(self.aprobar(s).fecha_decision,fecha)
        with self.assertRaises(ValidationError): self.aprobar(s,decision='RECHAZADA',motivo='Cambio')
        self.assertEqual(self.solicitar().pk,s.pk)
        self.assertEqual(SolicitudAcademica.objects.count(),1)

    def test_rechazo_no_toca_nota_ni_inscripcion(self):
        s=self.solicitar();antes=Calificacion.objects.values().get(pk=self.nota.pk)
        with self.assertRaises(ValidationError): self.aprobar(s,decision='RECHAZADA')
        self.aprobar(s,decision='RECHAZADA',motivo='No justificada')
        self.assertEqual(Calificacion.objects.values().get(pk=self.nota.pk),antes)
        self.assertEqual(InscripcionCurso.objects.get(pk=self.inscripcion.pk).estado,'APROBADA')
        s.refresh_from_db()
        self.assertEqual(s.aplicados,{})

    def test_rollback_nota_inscripcion_y_resolucion(self):
        s=self.solicitar()
        with patch.object(SolicitudAcademica,'save',side_effect=DatabaseError('Fallo de historial')):
            with self.assertRaises(DatabaseError): self.aprobar(s)
        self.recargar();s.refresh_from_db()
        self.assertEqual(self.nota.nota_final,Decimal('70'))
        self.assertEqual(self.inscripcion.estado,'APROBADA')
        self.assertEqual(s.estado,'PENDIENTE')
        self.assertIsNone(s.fecha_decision)

    def test_obsoleta_por_componentes_inscripcion_curso_o_asistencia(self):
        for modelo,campo,valor in [(Calificacion,'tarea_2',Decimal('61')),
                (InscripcionCurso,'motivo_cierre','Otro motivo'),(Curso,'horario','Otro horario')]:
            s=self.solicitar(clave=uuid.uuid4())
            registro=modelo.objects.get(pk={Calificacion:self.nota.pk,InscripcionCurso:self.inscripcion.pk,Curso:self.curso.pk}[modelo])
            original=getattr(registro,campo)
            modelo.objects.filter(pk=registro.pk).update(**{campo:valor})
            with self.assertRaisesMessage(ValidationError,'obsoleta'): self.aprobar(s)
            self.aprobar(s,decision='RECHAZADA',motivo='Cambió el registro')
            modelo.objects.filter(pk=registro.pk).update(**{campo:original})
        s=self.solicitar(clave=uuid.uuid4())
        Asistencia.objects.filter(inscripcion=self.inscripcion).update(observaciones='Cambio')
        with self.assertRaisesMessage(ValidationError,'obsoleta'): self.aprobar(s)

    def test_datos_cambiados_desde_formulario_no_generan_solicitud(self):
        revision=firma_nota(self.curso,self.inscripcion,self.nota)
        Calificacion.objects.filter(pk=self.nota.pk).update(observaciones='Cambio posterior')
        with self.assertRaisesMessage(ValidationError,'cambiaron'): self.solicitar(revision=revision)
        self.assertFalse(SolicitudAcademica.objects.exists())

    def test_reasignacion_y_permisos_actuales(self):
        from core.models import Usuario
        s=self.solicitar()
        otro=Maestro.objects.create(usuario=self.directora,nombres='Otra',apellidos='Docente',pais='SV',estado='ACTIVO')
        Curso.objects.filter(pk=self.curso.pk).update(maestro=otro)
        with self.assertRaises(ValidationError): self.aprobar(s)
        Curso.objects.filter(pk=self.curso.pk).update(maestro=self.maestro)
        Usuario.objects.filter(pk=self.docente.pk).update(estado_cuenta='BLOQUEADA')
        with self.assertRaises(ValidationError): self.aprobar(s)
        Usuario.objects.filter(pk=self.docente.pk).update(estado_cuenta='ACTIVA')
        for rol in ['ADMINISTRADOR','SECRETARIA','MAESTRO','ESTUDIANTE','PASTOR_PRINCIPAL']:
            Usuario.objects.filter(pk=self.directora.pk).update(rol=rol,is_superuser=True)
            with self.assertRaises(ValidationError): self.aprobar(s)

    def test_inasistencia_y_dos_ausencias_bloquean_sin_cambiar_registros(self):
        InscripcionCurso.objects.filter(pk=self.inscripcion.pk).update(estado='REPROBADA_POR_INASISTENCIA')
        with self.assertRaisesMessage(ValidationError,'inasistencia'): self.solicitar()
        InscripcionCurso.objects.filter(pk=self.inscripcion.pk).update(estado='APROBADA')
        ids=list(Asistencia.objects.filter(inscripcion=self.inscripcion).values_list('pk',flat=True))[:2]
        Asistencia.objects.filter(pk__in=ids).update(estado_asistencia='AUSENTE_INJUSTIFICADA')
        with self.assertRaisesMessage(ValidationError,'ausencias'): self.solicitar()
        self.assertFalse(SolicitudAcademica.objects.exists())

    def test_dos_ausencias_posteriores_a_solicitud_impiden_aprobar(self):
        s=self.solicitar()
        ids=list(Asistencia.objects.values_list('pk',flat=True))[:2]
        Asistencia.objects.filter(pk__in=ids).update(estado_asistencia='AUSENTE_INJUSTIFICADA')
        with self.assertRaises(ValidationError): self.aprobar(s)
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.nota_final,Decimal('70'))

    def test_no_crea_nota_ni_repara_inconsistencias(self):
        for cambios in [{'estado':'PENDIENTE'},{'nota_final':Decimal('99')},{'fecha_registro':None}]:
            antes=Calificacion.objects.values().get(pk=self.nota.pk)
            Calificacion.objects.filter(pk=self.nota.pk).update(**cambios)
            with self.assertRaises(ValidationError): self.solicitar()
            Calificacion.objects.filter(pk=self.nota.pk).update(**{k:antes[k] for k in cambios})
        self.nota.delete()
        with self.assertRaisesMessage(ValidationError,'No existe'): self.solicitar()
        self.assertFalse(Calificacion.objects.exists())

    def test_matricula_inactiva_curso_abierto_y_sin_cambios_bloquean(self):
        with self.assertRaisesMessage(ValidationError,'cambiar'): self.solicitar(componentes={c:getattr(self.nota,c) for c in Calificacion.COMPONENTES})
        Matricula.objects.filter(pk=self.inscripcion.matricula_id).update(estado='INACTIVA')
        with self.assertRaises(ValidationError): self.solicitar()
        Matricula.objects.filter(pk=self.inscripcion.matricula_id).update(estado='ACTIVA')
        Curso.objects.filter(pk=self.curso.pk).update(estado='ACTIVO')
        with self.assertRaises(ValidationError): self.solicitar()

    def test_protecciones_ordinarias_se_conservan_despues_de_aprobar(self):
        s=self.solicitar();self.aprobar(s);self.recargar()
        with self.assertRaises(ValidationError): self.nota.save()
        self.assertEqual(self.client.post(reverse('registrar_calificacion'),{'curso':self.curso.pk}).status_code,403)
        s.refresh_from_db()
        with self.assertRaises(ValidationError): s.save()
        with self.assertRaises(ValidationError): s.delete()

    def test_rutas_docente_directora_y_csrf(self):
        url=reverse('solicitar_correccion',args=[self.inscripcion.pk])
        response=self.client.get(url)
        self.assertContains(response,'Corrección excepcional',status_code=200)
        datos={'clave':self.clave,'motivo':'Corrección','revision':firma_nota(self.curso,self.inscripcion,self.nota),
               **self.componentes(),'accion':'comparar'}
        response=self.client.post(url,datos)
        self.assertContains(response,'71.00')
        self.assertFalse(SolicitudAcademica.objects.exists())
        datos['confirmacion']=response.context['form'].data['confirmacion']
        datos['accion']='enviar'
        self.assertEqual(self.client.post(url,datos).status_code,302)
        s=SolicitudAcademica.objects.get()
        detalle=reverse('solicitud_academica',args=[s.pk])
        self.assertEqual(self.client.post(detalle,{'decision':'APROBADA'}).status_code,403)
        self.client.force_login(self.directora)
        self.assertContains(self.client.get(reverse('solicitudes_academicas')),'Corrección de calificación')
        self.assertContains(self.client.get(detalle),'71.00')
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.directora)
        self.assertEqual(csrf.post(detalle,{'decision':'APROBADA'}).status_code,403)
        self.assertEqual(self.client.post(detalle,{'decision':'APROBADA'}).status_code,302)
        self.assertContains(self.client.get(detalle),'Nota aplicada')

    def test_identificadores_ajenos_y_administrador_sin_autoridad(self):
        otro=Maestro.objects.create(usuario=self.directora,nombres='Otra',apellidos='Docente',pais='SV',estado='ACTIVO')
        Curso.objects.filter(pk=self.curso.pk).update(maestro=otro)
        self.assertEqual(self.client.get(reverse('solicitar_correccion',args=[self.inscripcion.pk])).status_code,404)
        with self.assertRaises(ValidationError): self.solicitar()
        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(reverse('solicitar_correccion',args=[self.inscripcion.pk])).status_code,403)

    def test_restricciones_destino_y_pendientes_en_base(self):
        s=self.solicitar()
        with self.assertRaises(IntegrityError),transaction.atomic():
            SolicitudAcademica.objects.create(clave=uuid.uuid4(),tipo='CORRECCION_CALIFICACION',
                inscripcion=self.inscripcion,curso=self.curso,solicitante=self.docente,motivo='Duplicada',anteriores={})
        with self.assertRaises(IntegrityError),transaction.atomic():
            SolicitudAcademica.objects.filter(pk=s.pk).update(tipo='CANCELACION_SESION')

    def test_0002_solo_modifica_solicitud_y_0001_se_conserva(self):
        migration=importlib.import_module('academico.migrations.0002_correcciones_calificaciones').Migration
        self.assertIn(('academico','0001_initial'),migration.dependencies)
        for op in migration.operations:
            self.assertEqual(op.model_name,'solicitudacademica')

    def test_confirmacion_no_admite_cambios_silenciosos_ni_envio_sin_comparar(self):
        url=reverse('solicitar_correccion',args=[self.inscripcion.pk])
        datos={'clave':self.clave,'motivo':'Corrección','revision':firma_nota(self.curso,self.inscripcion,self.nota),
               **self.componentes(),'accion':'enviar'}
        self.assertContains(self.client.post(url,datos),'Compare nuevamente')
        self.assertFalse(SolicitudAcademica.objects.exists())
        datos['accion']='comparar'
        response=self.client.post(url,datos)
        datos['confirmacion']=response.context['form'].data['confirmacion']
        datos['accion']='enviar';datos['tarea_1']='72.50'
        self.assertContains(self.client.post(url,datos),'propuesta cambió')
        self.assertFalse(SolicitudAcademica.objects.exists())

    def test_correccion_de_componente_asistencia_no_toca_registros(self):
        antes=list(Asistencia.objects.values())
        s=self.solicitar(componentes=self.componentes(nota_asistencia=Decimal('35')))
        self.aprobar(s)
        self.assertEqual(list(Asistencia.objects.values()),antes)
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.nota_asistencia,Decimal('35'))

    def test_propuesta_no_puede_falsificar_nota_final(self):
        s=self.solicitar()
        propuesta=dict(s.propuestos,nota_final='100.00')
        SolicitudAcademica.objects.filter(pk=s.pk).update(propuestos=propuesta)
        with self.assertRaisesMessage(ValidationError,'cálculo del servidor'): self.aprobar(s)
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.nota_final,Decimal('70'))

    def test_historial_protege_tipo_destino_y_componentes(self):
        s=self.solicitar()
        s.tipo='CANCELACION_SESION'
        with self.assertRaises(ValidationError): s.save()
        s.refresh_from_db();s.propuestos={'componentes':{}}
        with self.assertRaises(ValidationError): s.save()
        s.refresh_from_db();self.aprobar(s);s.refresh_from_db()
        self.assertEqual(s.aplicados['ultima_correccion'],s.pk)
        with self.assertRaises(ValidationError): s.delete()

    def test_rollback_si_falla_inscripcion_despues_de_nota(self):
        from django.db.models.query import QuerySet
        original=QuerySet.update
        def actualizar(qs,**kwargs):
            if qs.model is InscripcionCurso: raise DatabaseError('Fallo simulado de inscripción')
            return original(qs,**kwargs)
        s=self.solicitar()
        with patch.object(QuerySet,'update',actualizar):
            with self.assertRaises(DatabaseError): self.aprobar(s)
        self.recargar();s.refresh_from_db()
        self.assertEqual(self.nota.nota_final,Decimal('70'))
        self.assertEqual(s.estado,'PENDIENTE')

    def test_migracion_preserva_cancelaciones_existentes_en_memoria_independiente(self):
        # Base adicional exclusivamente :memory:, sin registrar un alias persistente.
        from django.db import connection, connections
        from django.db.migrations.loader import MigrationLoader
        db=connection.copy(alias='prueba_migracion_solo_memoria')
        db.settings_dict['NAME']=':memory:'
        db.ensure_connection()
        connections[db.alias]=db
        try:
            loader=MigrationLoader(None)
            anterior=loader.project_state([('academico','0001_initial')])
            modelo=anterior.apps.get_model('academico','SolicitudAcademica')
            with db.cursor() as cursor:
                for tabla,columna in [('curso','id_curso'),('sesion_clase','id_sesion'),('usuario','id_usuario'),('inscripcion_curso','id_inscripcion')]:
                    cursor.execute(f'CREATE TABLE {tabla} ({columna} bigint PRIMARY KEY)')
                    cursor.execute(f'INSERT INTO {tabla} VALUES (1)')
            with db.schema_editor(atomic=False) as editor: editor.create_model(modelo)
            with db.cursor() as cursor:
                cursor.execute('''INSERT INTO solicitud_academica
                    (id,clave,curso_id,sesion_id,solicitante_id,motivo,estado,motivo_decision,fecha_solicitud,anteriores,propuestos,aplicados)
                    VALUES (1,%s,1,1,1,'Cancelación original','PENDIENTE','','2026-01-01 00:00:00','{}','{}','{}')''',[uuid.uuid4().hex])
            for operacion in loader.disk_migrations['academico','0002_correcciones_calificaciones'].operations:
                siguiente=anterior.clone()
                operacion.state_forwards('academico',siguiente)
                with db.schema_editor(atomic=False) as editor:
                    operacion.database_forwards('academico',editor,anterior,siguiente)
                anterior=siguiente
            with db.cursor() as cursor:
                cursor.execute('SELECT tipo,sesion_id,inscripcion_id,motivo,estado FROM solicitud_academica')
                self.assertEqual(cursor.fetchone(),('CANCELACION_SESION',1,None,'Cancelación original','PENDIENTE'))
                for tabla in ['curso','sesion_clase','usuario','inscripcion_curso']:
                    cursor.execute(f'SELECT * FROM {tabla}')
                    self.assertEqual(cursor.fetchall(),[(1,)])
        finally:
            db.connection.close()
            del connections[db.alias]

    def enviar_http(self, motivo='Corrección HTTP'):
        url=reverse('solicitar_correccion',args=[self.inscripcion.pk])
        datos={'clave':self.clave,'motivo':motivo,'revision':firma_nota(self.curso,self.inscripcion,self.nota),
               **self.componentes(),'accion':'comparar'}
        response=self.client.post(url,datos)
        datos['confirmacion']=response.context['form'].data['confirmacion']
        datos['accion']='enviar'
        self.assertEqual(self.client.post(url,datos).status_code,302)
        return url,datos,SolicitudAcademica.objects.get(clave=self.clave)

    def test_http_reenvio_identico_tras_aprobar_muestra_resultado_existente(self):
        url,datos,s=self.enviar_http()
        self.aprobar(s)
        nota_antes=Calificacion.objects.values().get(pk=self.nota.pk)
        inscripcion_antes=InscripcionCurso.objects.values().get(pk=self.inscripcion.pk)
        s.refresh_from_db();fecha=s.fecha_decision
        response=self.client.post(url,datos,follow=True)
        self.assertRedirects(response,reverse('solicitud_academica',args=[s.pk]))
        self.assertContains(response,'Solicitud ya registrada. Estado: Aprobada.')
        self.assertNotContains(response,'La propuesta debe cambiar')
        self.assertEqual(Calificacion.objects.values().get(pk=self.nota.pk),nota_antes)
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.inscripcion.pk),inscripcion_antes)
        s.refresh_from_db()
        self.assertEqual(s.fecha_decision,fecha)
        self.assertEqual(SolicitudAcademica.objects.count(),1)

    def test_http_reenvio_identico_tras_rechazar(self):
        url,datos,s=self.enviar_http()
        self.aprobar(s,decision='RECHAZADA',motivo='No procede')
        response=self.client.post(url,datos,follow=True)
        self.assertRedirects(response,reverse('solicitud_academica',args=[s.pk]))
        self.assertContains(response,'Solicitud ya registrada. Estado: Rechazada.')
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.nota_final,Decimal('70'))
        self.assertEqual(SolicitudAcademica.objects.count(),1)

    def test_http_uuid_reutilizado_no_admite_propuesta_motivo_o_inscripcion_distintos(self):
        url,datos,s=self.enviar_http()
        self.aprobar(s)
        for cambio in ({'tarea_1':'90.00'},{'motivo':'Otro motivo'}):
            with self.subTest(cambio=cambio):
                response=self.client.post(url,dict(datos,**cambio))
                self.assertEqual(response.status_code,200)
                self.assertNotIn('Location',response)
        # Otra inscripción del mismo maestro: no se acepta el UUID del primer destino.
        otra=InscripcionCurso.objects.exclude(pk=self.inscripcion.pk).first()
        response=self.client.post(reverse('solicitar_correccion',args=[otra.pk]),datos)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('Location',response)
        self.assertEqual(SolicitudAcademica.objects.count(),1)
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.nota_final,Decimal('71'))

    def test_http_uuid_ajeno_no_revela_solicitud_ni_permiso_por_clave(self):
        from core.models import Usuario
        from django.core import signing
        url,datos,s=self.enviar_http(motivo='JUSTIFICACION PRIVADA ORIGINAL')
        nuevo=Usuario.objects.create_user('doc-audit','doc-audit@example.test','clave',rol='MAESTRO')
        maestro=Maestro.objects.create(usuario=nuevo,nombres='Nuevo',apellidos='Docente',pais='SV',estado='ACTIVO')
        Curso.objects.filter(pk=self.curso.pk).update(maestro=maestro)
        self.client.force_login(nuevo)
        response=self.client.get(url)
        self.assertContains(response,'Ya existe una corrección pendiente')
        self.assertNotContains(response,'Consultar solicitud pendiente')
        self.assertNotContains(response,'JUSTIFICACION PRIVADA ORIGINAL')
        # Aun disponiendo del POST antiguo completo, el UUID no concede acceso.
        response=self.client.post(url,datos)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('Location',response)
        self.assertNotContains(response,'Nota propuesta:')
        self.assertEqual(self.client.get(reverse('solicitud_academica',args=[s.pk])).status_code,404)
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.nota_final,Decimal('70'))
        self.assertEqual(SolicitudAcademica.objects.count(),1)

    def test_pendiente_bloquea_formulario_comparacion_y_ofrece_enlace_permitido(self):
        url,datos,s=self.enviar_http()
        response=self.client.get(url)
        self.assertContains(response,'Ya existe una corrección pendiente')
        self.assertContains(response,reverse('solicitud_academica',args=[s.pk]))
        self.assertNotContains(response,'Comparar propuesta')
        self.assertNotContains(response,'Enviar solicitud a Dirección')
        datos=dict(datos,clave=uuid.uuid4(),accion='comparar')
        response=self.client.post(url,datos)
        self.assertContains(response,'Ya existe una corrección pendiente')
        self.assertNotContains(response,'Resultado propuesto:')
        self.assertEqual(SolicitudAcademica.objects.count(),1)

    def test_no_hay_helper_publico_de_escritura_y_decision_directa_docente_no_modifica(self):
        from . import correcciones
        s=self.solicitar()
        antes=Calificacion.objects.values().get(pk=self.nota.pk)
        antes_inscripcion=InscripcionCurso.objects.values().get(pk=self.inscripcion.pk)
        with self.assertRaises(AttributeError):
            correcciones.aprobar_correccion(s,self.curso,self.docente,self.inscripcion,self.nota)
        with self.assertRaises(ValidationError):
            decidir(solicitud_id=s.pk,usuario=self.docente,decision='APROBADA')
        self.assertEqual(Calificacion.objects.values().get(pk=self.nota.pk),antes)
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.inscripcion.pk),antes_inscripcion)
        s.refresh_from_db()
        self.assertEqual(s.estado,'PENDIENTE')

    def test_escritura_excepcional_ocurre_solo_tras_bloqueos_y_dentro_transaccion(self):
        from django.db import connection
        from django.db.models.query import QuerySet
        lock_original=QuerySet.select_for_update
        update_original=QuerySet.update
        bloqueados=[];escrituras=[]
        def bloquear(qs,*args,**kwargs):
            bloqueados.append(qs.model.__name__)
            return lock_original(qs,*args,**kwargs)
        def actualizar(qs,**kwargs):
            if qs.model in (Calificacion,InscripcionCurso):
                self.assertTrue(connection.in_atomic_block)
                for nombre in ['Usuario','Curso','Maestro','Matricula','InscripcionCurso','Asistencia','Calificacion','SolicitudAcademica']:
                    self.assertIn(nombre,bloqueados)
                escrituras.append(qs.model.__name__)
            return update_original(qs,**kwargs)
        s=self.solicitar()
        with patch.object(QuerySet,'select_for_update',bloquear),patch.object(QuerySet,'update',actualizar):
            self.aprobar(s)
        self.assertEqual(escrituras,['Calificacion','InscripcionCurso'])
        s.refresh_from_db()
        self.assertEqual(s.estado,'APROBADA')
