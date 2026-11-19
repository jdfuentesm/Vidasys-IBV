"""Ciclo docente confirmado; solo SQLite aislado y datos ficticios."""
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Usuario
from .test_flujo import FlujoAcademicoTests
from .flujo import (actualizar_sesion, cerrar_curso, firma_calendario, firma_cierre,
                    matricular, requisitos_cierre, resumen_docente)
from .models import Asistencia, Calificacion, Curso, Estudiante, InscripcionCurso, Matricula, SesionClase


class CicloDocenteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        FlujoAcademicoTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.curso = self.cursos[0]
        _, inscripciones, _ = matricular(estudiante=self.estudiante, ciclo=self.ciclo,
            numero_matricula='CICLO-1', fecha_matricula=date(2026,1,2))
        self.inscripcion = inscripciones[0]
        for n in range(1,6):
            SesionClase.objects.create(curso=self.curso, numero_clase=n, fecha=date(2026,2,n),
                hora_inicio=time(8), hora_fin=time(9), estado='IMPARTIDA')
        self.client.force_login(self.docente)

    def nota(self, inscripcion=None, valor=Decimal('70')):
        componentes = dict(nota_asistencia=Decimal('40'), nota_uniforme=Decimal('20'),
            nota_participacion=Decimal('20'), nota_companerismo=Decimal('20'), puntos_extras=Decimal('0'),
            tarea_1=valor, examen_1=valor, tarea_2=valor, examen_2=valor)
        return Calificacion.objects.create(inscripcion=inscripcion or self.inscripcion, **componentes)

    def completar_asistencia(self):
        for inscripcion in InscripcionCurso.objects.filter(curso=self.curso, estado='CURSANDO'):
            for sesion in SesionClase.objects.filter(curso=self.curso, estado='IMPARTIDA'):
                if sesion.fecha >= inscripcion.fecha_inscripcion:
                    Asistencia.objects.get_or_create(inscripcion=inscripcion, sesion=sesion,
                                                    defaults={'estado_asistencia': 'PRESENTE'})

    def firma(self):
        self.curso.refresh_from_db()
        return firma_cierre(self.curso, list(SesionClase.objects.filter(curso=self.curso).order_by('numero_clase')))

    def cerrar(self, revision=None):
        return cerrar_curso(self.curso.pk, self.docente, revision or self.firma())

    def sesion_pendiente(self):
        return SesionClase.objects.create(curso=self.curso, numero_clase=6, fecha=date(2026,2,6),
            hora_inicio=time(8), hora_fin=time(9), estado='PROGRAMADA')

    def datos_sesion(self, sesion, **cambios):
        return dict(fecha=sesion.fecha, hora_inicio=sesion.hora_inicio, hora_fin=sesion.hora_fin,
                    estado=sesion.estado) | cambios

    def actualizar(self, sesion, **cambios):
        firma = firma_calendario(self.curso, list(SesionClase.objects.filter(curso=self.curso).order_by('numero_clase')))
        return actualizar_sesion(self.curso.pk, sesion.pk, self.docente, self.datos_sesion(sesion, **cambios), firma)

    def test_nota_provisional_actualizable_y_asistencia_posterior(self):
        nota = self.nota()
        self.assertEqual(nota.estado, 'PENDIENTE')
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, 'CURSANDO')
        self.assertIsNone(self.inscripcion.fecha_cierre)
        Asistencia.objects.create(inscripcion=self.inscripcion, sesion=SesionClase.objects.get(curso=self.curso,numero_clase=1), estado_asistencia='PRESENTE')
        nota.tarea_1=Decimal('80');nota.save()
        self.assertEqual(Calificacion.objects.count(), 1)
        self.inscripcion.refresh_from_db();self.assertEqual(self.inscripcion.estado, 'CURSANDO')

    def test_aprobacion_definitiva_desde_setenta(self):
        self.completar_asistencia()
        # (100 + 4 * 62.5) / 5 = 70.
        nota=self.nota(valor=Decimal('62.5'))
        self.assertEqual(nota.nota_final, Decimal('70'))
        self.cerrar();nota.refresh_from_db();self.inscripcion.refresh_from_db()
        self.assertEqual(nota.estado, 'APROBADA')
        self.assertEqual(self.inscripcion.estado, 'APROBADA')
        self.assertIsNotNone(self.inscripcion.fecha_cierre)

    def test_reprobacion_definitiva_inferior_setenta(self):
        self.completar_asistencia()
        nota=self.nota(valor=Decimal('62.49'))
        self.cerrar();nota.refresh_from_db();self.inscripcion.refresh_from_db()
        self.assertLess(nota.nota_final,70)
        self.assertEqual(self.inscripcion.estado,'REPROBADA_ACADEMICAMENTE')

    def test_cero_es_evaluacion_y_falta_de_fila_bloquea(self):
        self.completar_asistencia()
        with self.assertRaises(ValidationError): self.cerrar()
        self.assertFalse(Calificacion.objects.exists())
        self.nota(valor=Decimal('0'));self.cerrar()
        self.inscripcion.refresh_from_db();self.assertEqual(self.inscripcion.estado,'REPROBADA_ACADEMICAMENTE')

    def test_componente_invalido_impide_cierre(self):
        nota=self.nota()
        Calificacion.objects.filter(pk=nota.pk).update(tarea_1=Decimal('101'))
        with self.assertRaises(ValidationError):self.cerrar()
        self.curso.refresh_from_db();self.assertEqual(self.curso.estado,'ACTIVO')

    def test_dos_ausencias_preservadas_sin_exigir_nota(self):
        for n in (1,2):
            Asistencia.objects.create(inscripcion=self.inscripcion, sesion=SesionClase.objects.get(curso=self.curso,numero_clase=n),estado_asistencia='AUSENTE_INJUSTIFICADA')
        antes=InscripcionCurso.objects.values().get(pk=self.inscripcion.pk)
        self.cerrar()
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.inscripcion.pk),antes)
        self.assertEqual(antes['estado'],'REPROBADA_POR_INASISTENCIA')

    def test_reintento_de_cierre_no_duplica_ni_modifica(self):
        self.completar_asistencia()
        self.nota();firma=self.firma();self.cerrar(firma)
        antes=list(InscripcionCurso.objects.values());notas=list(Calificacion.objects.values())
        self.cerrar(firma)
        self.assertEqual(list(InscripcionCurso.objects.values()),antes)
        self.assertEqual(list(Calificacion.objects.values()),notas)

    def test_firma_obsoleta_por_cambio_de_nota_rechazada(self):
        self.completar_asistencia()
        nota=self.nota();firma=self.firma();nota.tarea_1=Decimal('90');nota.save()
        with self.assertRaises(ValidationError):self.cerrar(firma)
        self.curso.refresh_from_db();self.assertEqual(self.curso.estado,'ACTIVO')

    def test_fallo_al_final_revierte_resultados(self):
        self.completar_asistencia()
        self.nota();firma=self.firma()
        antes=list(InscripcionCurso.objects.values());notas=list(Calificacion.objects.values())
        with patch.object(Curso,'save',side_effect=DatabaseError('fallo simulado')):
            with self.assertRaises(DatabaseError):self.cerrar(firma)
        self.assertEqual(list(InscripcionCurso.objects.values()),antes)
        self.assertEqual(list(Calificacion.objects.values()),notas)
        self.curso.refresh_from_db();self.assertEqual(self.curso.estado,'ACTIVO')

    def test_bloqueo_tras_cierre_modelo_y_post_web(self):
        self.completar_asistencia()
        nota=self.nota();self.cerrar()
        nota.tarea_1=Decimal('90')
        with self.assertRaises(ValidationError):nota.save()
        with self.assertRaises(ValidationError):
            Asistencia.objects.create(inscripcion=self.inscripcion,sesion=SesionClase.objects.get(curso=self.curso,numero_clase=1),estado_asistencia='PRESENTE')
        for ruta in ('registrar_asistencia','registrar_calificacion'):
            self.assertEqual(self.client.post(reverse(ruta),{'curso':self.curso.pk,'sesion':1}).status_code,403)
            self.assertEqual(self.client.get(reverse(ruta),{'curso':self.curso.pk}).status_code,200)

    def test_docente_ajeno_no_cierra_ni_modifica_sesiones(self):
        otro=Usuario.objects.create_user('ajeno-ciclo','ajeno@example.test','clave',rol='MAESTRO')
        sesion=self.sesion_pendiente()
        with self.assertRaises(ValidationError):cerrar_curso(self.curso.pk,otro,self.firma())
        with self.assertRaises(ValidationError):actualizar_sesion(self.curso.pk,sesion.pk,otro,self.datos_sesion(sesion),'')
        self.client.force_login(otro)
        for ruta,args in [('gestionar_sesion',[self.curso.pk,sesion.pk]),('cierre_curso',[self.curso.pk])]:
            self.assertEqual(self.client.get(reverse(ruta,args=args)).status_code,404)

    def test_suspender_reprogramar_e_impartir_por_web(self):
        sesion=self.sesion_pendiente();url=reverse('gestionar_sesion',args=[self.curso.pk,sesion.pk])
        for estado in ('SUSPENDIDA','PROGRAMADA','IMPARTIDA'):
            response=self.client.get(url)
            datos={'fecha':'2026-02-06','hora_inicio':'08:00','hora_fin':'09:00','estado':estado,'revision':response.context['form'].initial['revision']}
            self.assertEqual(self.client.post(url,datos).status_code,302)
            sesion.refresh_from_db();self.assertEqual(sesion.estado,estado)
        self.assertEqual(self.client.post(url,datos).status_code,403)

    def test_no_impartir_futura_ni_suspender_con_asistencia(self):
        sesion=self.sesion_pendiente()
        SesionClase.objects.filter(pk=sesion.pk).update(fecha=timezone.localdate()+timedelta(days=1))
        sesion.refresh_from_db()
        with self.assertRaises(ValidationError):self.actualizar(sesion,estado='IMPARTIDA')
        SesionClase.objects.filter(pk=sesion.pk).update(fecha=date(2026,2,6));sesion.refresh_from_db()
        Asistencia.objects.create(inscripcion=self.inscripcion,sesion=sesion,estado_asistencia='PRESENTE')
        with self.assertRaises(ValidationError):self.actualizar(sesion,estado='SUSPENDIDA')
        with self.assertRaises(ValidationError):self.actualizar(sesion,fecha=date(2026,2,7))

    def test_sesion_revision_fecha_y_csrf(self):
        sesion=self.sesion_pendiente()
        with self.assertRaises(ValidationError):actualizar_sesion(self.curso.pk,sesion.pk,self.docente,self.datos_sesion(sesion),'obsoleta')
        with self.assertRaises(ValidationError):self.actualizar(sesion,fecha=date(2027,1,1))
        cliente=Client(enforce_csrf_checks=True);cliente.force_login(self.docente)
        self.assertEqual(cliente.post(reverse('gestionar_sesion',args=[self.curso.pk,sesion.pk]),{}).status_code,403)
        self.assertEqual(cliente.post(reverse('cierre_curso',args=[self.curso.pk]),{}).status_code,403)

    def test_resumen_y_requisitos_visibles(self):
        self.sesion_pendiente()
        resumen=resumen_docente(self.curso)
        self.assertEqual(resumen['notas_pendientes'],1)
        self.assertEqual(resumen['asistencias_pendientes'],5)
        self.assertEqual(resumen['sesiones_pendientes'],1)
        self.assertContains(self.client.get(reverse('mis_cursos')),'Evaluaciones sin registrar: 1')
        self.assertContains(self.client.get(reverse('cierre_curso',args=[self.curso.pk])),'faltan calificaciones obligatorias')

    def test_fallo_en_segunda_inscripcion_revierte_todo_el_lote(self):
        otro=Estudiante.objects.create(codigo_estudiante='CICLO-OTRO',nombres='Otro',apellidos='Ficticio',fecha_ingreso=date(2026,1,1),estado='ACTIVO')
        _,inscripciones,_=matricular(estudiante=otro,ciclo=self.ciclo,numero_matricula='CICLO-2',fecha_matricula=date(2026,1,2))
        self.nota();self.nota(inscripcion=inscripciones[0]);self.completar_asistencia()
        antes=list(InscripcionCurso.objects.values());notas=list(Calificacion.objects.values());firma=self.firma()
        guardar=InscripcionCurso.save
        contador=[0]
        def fallo(obj,*args,**kwargs):
            contador[0]+=1
            if contador[0]==2:raise DatabaseError('fallo intermedio')
            return guardar(obj,*args,**kwargs)
        with patch.object(InscripcionCurso,'save',fallo):
            with self.assertRaises(DatabaseError):self.cerrar(firma)
        self.assertEqual(list(InscripcionCurso.objects.values()),antes)
        self.assertEqual(list(Calificacion.objects.values()),notas)

    def test_curso_cancelado_y_sesion_no_se_reabren(self):
        sesion=self.sesion_pendiente()
        self.curso.estado='CANCELADO';self.curso.save()
        with self.assertRaises(ValidationError):self.actualizar(sesion,estado='IMPARTIDA')
        with self.assertRaises(ValidationError):self.cerrar()
        self.assertEqual(self.client.post(reverse('gestionar_sesion',args=[self.curso.pk,sesion.pk]),{}).status_code,403)

    def test_reglas_sesion_no_permiten_cancelacion_ni_hora_invalida(self):
        sesion=self.sesion_pendiente()
        with self.assertRaises(ValidationError):self.actualizar(sesion,estado='CANCELADA')
        with self.assertRaises(ValidationError):self.actualizar(sesion,hora_fin=time(7))

    def test_roles_no_docentes_no_gestionan_sesion(self):
        sesion=self.sesion_pendiente()
        for usuario in (self.directora,self.secretaria):
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(reverse('gestionar_sesion',args=[self.curso.pk,sesion.pk]),{}).status_code,403)

    def test_cierre_bloqueado_por_asistencia_ausente_sin_inventar_faltas(self):
        self.nota()
        with self.assertRaisesMessage(ValidationError, 'registros válidos de asistencia'):
            self.cerrar()
        self.assertFalse(Asistencia.objects.exists())
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, 'CURSANDO')
        self.assertIsNone(self.inscripcion.fecha_cierre)
        detalle=resumen_docente(self.curso)
        self.assertEqual(detalle['asistencias_pendientes'],5)
        self.assertEqual(len(detalle['detalle_asistencia']),5)

    def test_cierre_web_completo_y_reintento_seguro(self):
        self.nota();self.completar_asistencia()
        url=reverse('cierre_curso',args=[self.curso.pk]);revision=self.firma()
        self.assertEqual(self.client.post(url,{'revision':revision}).status_code,302)
        antes=list(InscripcionCurso.objects.values());notas=list(Calificacion.objects.values());asistencias=list(Asistencia.objects.values())
        self.assertEqual(self.client.post(url,{'revision':revision}).status_code,302)
        self.assertEqual(list(InscripcionCurso.objects.values()),antes)
        self.assertEqual(list(Calificacion.objects.values()),notas)
        self.assertEqual(list(Asistencia.objects.values()),asistencias)

    def test_asistencia_pendiente_identifica_sesion_estudiante_y_enlace(self):
        self.nota();self.completar_asistencia()
        Asistencia.objects.filter(inscripcion=self.inscripcion,sesion__numero_clase=3).delete()
        for url in [reverse('mis_cursos'),reverse('cierre_curso',args=[self.curso.pk])]:
            respuesta=self.client.get(url)
            self.assertContains(respuesta,'Clase 3')
            self.assertContains(respuesta,'sin asistencia registrada')
            self.assertContains(respuesta,self.estudiante.codigo_estudiante)
            sesion=SesionClase.objects.get(curso=self.curso,numero_clase=3)
            self.assertContains(respuesta,f'?curso={self.curso.pk}&amp;sesion={sesion.pk}')
        self.assertNotContains(self.client.get(reverse('cierre_curso',args=[self.curso.pk])),'Confirmar cierre académico')

    def test_no_exige_asistencia_cancelada_programada_o_suspendida(self):
        self.nota();self.completar_asistencia()
        sesion=self.sesion_pendiente()
        for estado in ('PROGRAMADA','SUSPENDIDA','CANCELADA'):
            # Fixture de estados históricos; no simula una autorización en la aplicación.
            SesionClase.objects.filter(pk=sesion.pk).update(estado=estado)
            self.assertEqual(resumen_docente(self.curso)['asistencias_pendientes'],0)
        self.cerrar()
        self.curso.refresh_from_db();self.assertEqual(self.curso.estado,'FINALIZADO')

    def test_extraordinaria_impartida_requiere_asistencia(self):
        self.nota();self.completar_asistencia()
        sesion=SesionClase.objects.create(curso=self.curso,numero_clase=7,fecha=date(2026,2,7),
            hora_inicio=time(8),hora_fin=time(9),estado='IMPARTIDA',motivo_extension='Clase extraordinaria ficticia',
            usuario_autoriza=self.directora,fecha_autorizacion=timezone.now())
        with self.assertRaisesMessage(ValidationError,'Clase 7'):self.cerrar()
        Asistencia.objects.create(inscripcion=self.inscripcion,sesion=sesion,estado_asistencia='AUSENTE_JUSTIFICADA')
        self.cerrar()

    def test_no_exige_sesion_anterior_a_inscripcion(self):
        self.nota()
        InscripcionCurso.objects.filter(pk=self.inscripcion.pk).update(fecha_inscripcion=date(2026,2,3))
        self.completar_asistencia()
        self.assertEqual(Asistencia.objects.count(),3)
        self.assertEqual(resumen_docente(self.curso)['asistencias_pendientes'],0)
        self.cerrar()

    def test_cierre_por_inasistencia_con_pendiente_previo_requiere_direccion(self):
        for n in (2,3):
            Asistencia.objects.create(inscripcion=self.inscripcion,sesion=SesionClase.objects.get(curso=self.curso,numero_clase=n),estado_asistencia='AUSENTE_INJUSTIFICADA')
        antes=InscripcionCurso.objects.values().get(pk=self.inscripcion.pk)
        with self.assertRaisesMessage(ValidationError,'Clase 1'):self.cerrar()
        resumen=resumen_docente(self.curso)
        self.assertEqual(resumen['asistencias_pendientes'],1)
        self.assertTrue(resumen['detalle_asistencia'][0]['faltantes'][0]['requiere_direccion'])
        self.assertEqual(InscripcionCurso.objects.values().get(pk=self.inscripcion.pk),antes)
        self.assertContains(self.client.get(reverse('cierre_curso',args=[self.curso.pk])),'Requiere revisión de Dirección')

    def test_inasistencia_inconsistente_no_se_corrige_silenciosamente(self):
        InscripcionCurso.objects.filter(pk=self.inscripcion.pk).update(estado='REPROBADA_POR_INASISTENCIA',fecha_cierre=date(2026,2,2))
        with self.assertRaisesMessage(ValidationError,'cierre por inasistencia inconsistente'):self.cerrar()
        self.assertFalse(Asistencia.objects.exists())

    def test_cambio_asistencia_invalida_firma_de_cierre(self):
        self.nota();self.completar_asistencia();firma=self.firma()
        registro=Asistencia.objects.filter(inscripcion=self.inscripcion).first()
        registro.estado_asistencia='AUSENTE_JUSTIFICADA';registro.save()
        with self.assertRaisesMessage(ValidationError,'asistencia o las notas cambiaron'):self.cerrar(firma)
        self.curso.refresh_from_db();self.assertEqual(self.curso.estado,'ACTIVO')

    def test_directora_y_admin_no_pueden_cancelar_por_via_docente(self):
        sesion=self.sesion_pendiente()
        admin=Usuario.objects.create_user('admin-finalizacion','admin-finalizacion@example.test','clave',rol='ADMINISTRADOR')
        for usuario in (self.docente,self.directora,admin):
            firma=firma_calendario(self.curso,list(SesionClase.objects.filter(curso=self.curso).order_by('numero_clase')))
            with self.assertRaises(ValidationError):
                actualizar_sesion(self.curso.pk,sesion.pk,usuario,self.datos_sesion(sesion,estado='CANCELADA'),firma)
            self.client.force_login(usuario)
            respuesta=self.client.post(reverse('gestionar_sesion',args=[self.curso.pk,sesion.pk]),{
                'fecha':'2026-02-06','hora_inicio':'08:00','hora_fin':'09:00','estado':'CANCELADA','revision':firma})
            self.assertEqual(respuesta.status_code,200 if usuario==self.docente else 403)
        sesion.refresh_from_db();self.assertEqual(sesion.estado,'PROGRAMADA')

    def test_admin_tecnico_no_cancela_ni_elimina_sesion(self):
        admin=Usuario.objects.create_superuser('tecnico-sesion','tecnico-sesion@example.test','Clave-Admin-Ficticia-72!',rol='ADMINISTRADOR')
        self.client.force_login(admin)
        sesion=self.sesion_pendiente();antes=SesionClase.objects.values().get(pk=sesion.pk)
        respuesta=self.client.post(reverse('admin:academico_sesionclase_change',args=[sesion.pk]),{
            'curso':self.curso.pk,'numero_clase':6,'fecha':'2026-02-06','hora_inicio':'08:00',
            'hora_fin':'09:00','estado':'CANCELADA','_save':'Guardar'})
        self.assertEqual(respuesta.status_code,200)
        self.assertContains(respuesta,'Solo Dirección puede aprobar una cancelación con trazabilidad')
        self.assertEqual(SesionClase.objects.values().get(pk=sesion.pk),antes)
        self.assertEqual(self.client.post(reverse('admin:academico_sesionclase_delete',args=[sesion.pk]),{'post':'yes'}).status_code,403)

    def test_admin_no_corrige_ni_borra_registros_finalizados(self):
        self.nota();self.completar_asistencia();self.cerrar()
        admin=Usuario.objects.create_superuser('tecnico-cierre','tecnico-cierre@example.test','Clave-Admin-Ficticia-72!',rol='ADMINISTRADOR')
        self.client.force_login(admin)
        antes=list(Asistencia.objects.values());notas=list(Calificacion.objects.values())
        registros=[('asistencia',Asistencia.objects.filter(inscripcion=self.inscripcion).first().pk),
                   ('calificacion',Calificacion.objects.get(inscripcion=self.inscripcion).pk),
                   ('sesionclase',SesionClase.objects.filter(curso=self.curso).first().pk),
                   ('curso',self.curso.pk),('inscripcioncurso',self.inscripcion.pk)]
        for modelo,pk in registros:
            for accion in ('change','delete'):
                self.assertEqual(self.client.post(reverse(f'admin:academico_{modelo}_{accion}',args=[pk]),{'post':'yes'}).status_code,403)
            respuesta=self.client.post(reverse(f'admin:academico_{modelo}_changelist'),{'action':'delete_selected','_selected_action':[pk],'post':'yes'})
            self.assertIn(respuesta.status_code,(200,302))
        self.assertEqual(list(Asistencia.objects.values()),antes)
        self.assertEqual(list(Calificacion.objects.values()),notas)

    def test_admin_no_omite_requisitos_de_cierre(self):
        admin=Usuario.objects.create_superuser('tecnico-cerrar','tecnico-cerrar@example.test','Clave-Admin-Ficticia-72!',rol='ADMINISTRADOR')
        self.client.force_login(admin)
        respuesta=self.client.post(reverse('admin:academico_curso_change',args=[self.curso.pk]),{
            'materia':self.curso.materia_id,'maestro':self.curso.maestro_id,'ciclo':self.curso.ciclo_id,
            'fecha_inicio':'2026-01-01','fecha_fin':'2026-12-31','modalidad':'PRESENCIAL','estado':'FINALIZADO','_save':'Guardar'})
        self.assertEqual(respuesta.status_code,200)
        self.assertContains(respuesta,'El cierre académico debe realizarse desde el flujo institucional docente')
        self.curso.refresh_from_db();self.assertEqual(self.curso.estado,'ACTIVO')

    def test_autorizar_extraordinaria_no_es_via_de_cancelacion(self):
        from .flujo import autorizar_extra
        sesion=SesionClase(curso=self.curso,numero_clase=7,fecha=date(2026,2,7),
            hora_inicio=time(8),hora_fin=time(9),estado='CANCELADA',motivo_extension='Ficticio')
        with self.assertRaisesMessage(ValidationError,'cancelación requiere una solicitud'):
            autorizar_extra(sesion,self.directora)
        self.assertFalse(SesionClase.objects.filter(curso=self.curso,numero_clase=7).exists())

    def test_asistencia_invalida_y_estado_inconsistente_bloquean(self):
        self.nota();self.completar_asistencia()
        Asistencia.objects.filter(inscripcion=self.inscripcion,sesion__numero_clase=1).update(estado_asistencia='INVALIDO')
        with self.assertRaisesMessage(ValidationError,'registros válidos de asistencia'):self.cerrar()
        Asistencia.objects.filter(inscripcion=self.inscripcion,sesion__numero_clase__in=[1,2]).update(estado_asistencia='AUSENTE_INJUSTIFICADA')
        with self.assertRaisesMessage(ValidationError,'dos ausencias injustificadas sin cierre'):self.cerrar()
        self.inscripcion.refresh_from_db();self.assertEqual(self.inscripcion.estado,'CURSANDO')
