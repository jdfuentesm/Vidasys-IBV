from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class Estudiante(models.Model):
    id_estudiante = models.BigAutoField(primary_key=True)

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        db_column="id_usuario",
        null=True,
        blank=True,
        related_name="perfil_estudiante",
    )

    codigo_estudiante = models.CharField(max_length=30, unique=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    telefono = models.CharField(max_length=25, null=True, blank=True)
    correo = models.EmailField(max_length=150, null=True, blank=True)
    direccion = models.TextField(null=True, blank=True)
    fecha_ingreso = models.DateField()
    estado = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "estudiante"
        verbose_name = "Estudiante"
        verbose_name_plural = "Estudiantes"

    def __str__(self):
        return f"{self.codigo_estudiante} - {self.nombres} {self.apellidos}"


class Maestro(models.Model):
    id_maestro = models.BigAutoField(primary_key=True)

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        db_column="id_usuario",
        null=True,
        blank=True,
        related_name="perfil_maestro",
    )

    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    telefono = models.CharField(max_length=25, null=True, blank=True)
    correo = models.EmailField(max_length=150, null=True, blank=True)
    pais = models.CharField(max_length=80)
    estado = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "maestro"
        verbose_name = "Maestro"
        verbose_name_plural = "Maestros"

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"


class Materia(models.Model):
    CICLOS_FORMATIVOS = (
        (1, "Ciclo I"),
        (2, "Ciclo II"),
        (3, "Ciclo III"),
        (4, "Ciclo IV"),
    )

    id_materia = models.BigAutoField(primary_key=True)
    codigo_materia = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)

    numero_ciclo_formativo = models.SmallIntegerField(
        choices=CICLOS_FORMATIVOS,
        verbose_name="Ciclo formativo",
    )

    estado = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "materia"
        verbose_name = "Materia"
        verbose_name_plural = "Materias"

    def __str__(self):
        nombre_ciclo = dict(self.CICLOS_FORMATIVOS).get(
            self.numero_ciclo_formativo,
            f"Ciclo {self.numero_ciclo_formativo}",
        )
        return f"{self.codigo_materia} - {self.nombre} ({nombre_ciclo})"


class CicloAcademico(models.Model):
    id_ciclo = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    numero_ciclo = models.SmallIntegerField()
    anio = models.SmallIntegerField()
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "ciclo_academico"
        verbose_name = "Ciclo académico"
        verbose_name_plural = "Ciclos académicos"
        unique_together = (("numero_ciclo", "anio"),)

    def __str__(self):
        return f"{self.nombre} - {self.anio}"


class Curso(models.Model):
    id_curso = models.BigAutoField(primary_key=True)

    ESTADOS_CURSO = (
        ("PROGRAMADO", "Programado"),
        ("ACTIVO", "Activo"),
        ("FINALIZADO", "Finalizado"),
        ("CANCELADO", "Cancelado"),
    )

    materia = models.ForeignKey(
        Materia,
        on_delete=models.PROTECT,
        db_column="id_materia",
        related_name="cursos",
    )

    maestro = models.ForeignKey(
        Maestro,
        on_delete=models.PROTECT,
        db_column="id_maestro",
        related_name="cursos",
    )

    ciclo = models.ForeignKey(
        CicloAcademico,
        on_delete=models.PROTECT,
        db_column="id_ciclo",
        related_name="cursos",
    )

    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    modalidad = models.CharField(max_length=20)
    horario = models.CharField(max_length=150, null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS_CURSO)

    def clean(self):
        super().clean()
        errores = {}

        materia = None
        ciclo = None

        if self.__dict__.get("materia_id") is not None:
            materia = self.materia

        if self.__dict__.get("ciclo_id") is not None:
            ciclo = self.ciclo

        # La materia debe pertenecer al mismo número de ciclo formativo.
        if (
            materia is not None
            and ciclo is not None
            and materia.numero_ciclo_formativo != ciclo.numero_ciclo
        ):
            errores["materia"] = (
                f"La materia pertenece al ciclo formativo "
                f"{materia.numero_ciclo_formativo}, pero el ciclo académico "
                f"seleccionado es el número {ciclo.numero_ciclo}."
            )

        # La fecha final no puede ser anterior a la inicial.
        if (
            self.fecha_inicio is not None
            and self.fecha_fin is not None
            and self.fecha_fin < self.fecha_inicio
        ):
            errores["fecha_fin"] = (
                "La fecha final del curso no puede ser anterior a la fecha inicial."
            )

        # Las fechas del curso deben estar dentro del ciclo académico.
        if (
            ciclo is not None
            and self.fecha_inicio is not None
            and not ciclo.fecha_inicio <= self.fecha_inicio <= ciclo.fecha_fin
        ):
            errores["fecha_inicio"] = (
                "La fecha inicial del curso debe estar dentro "
                "del período del ciclo académico."
            )

        if (
            ciclo is not None
            and self.fecha_fin is not None
            and not ciclo.fecha_inicio <= self.fecha_fin <= ciclo.fecha_fin
        ):
            errores["fecha_fin"] = (
                "La fecha final del curso debe estar dentro "
                "del período del ciclo académico."
            )

        # Para finalizar un curso deben haberse realizado entre 5 y 8 clases.
        if self.estado == "FINALIZADO":
            if self.pk is None:
                errores["estado"] = (
                    "Primero debe guardar el curso antes de poder finalizarlo."
                )
            else:
                sesiones_curso = SesionClase.objects.filter(curso_id=self.pk)

                cantidad_impartidas = sesiones_curso.filter(estado="IMPARTIDA").count()

                cantidad_pendientes = sesiones_curso.filter(
                    estado__in=("PROGRAMADA", "SUSPENDIDA")
                ).count()

                if cantidad_impartidas < 5:
                    errores["estado"] = (
                        "El curso no puede finalizar porque debe tener "
                        "al menos 5 clases impartidas."
                    )
                elif cantidad_impartidas > 8:
                    errores["estado"] = (
                        "El curso no puede tener más de 8 clases impartidas."
                    )

                if cantidad_pendientes > 0:
                    errores["estado"] = (
                        errores.get("estado", "")
                        + " No deben quedar sesiones programadas o suspendidas "
                        "al finalizar el curso."
                    ).strip()

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        managed = False
        db_table = "curso"
        verbose_name = "Curso"
        verbose_name_plural = "Cursos"
        unique_together = (("materia", "ciclo"),)

    def __str__(self):
        return f"{self.materia.nombre} - {self.ciclo}"


class Matricula(models.Model):
    id_matricula = models.BigAutoField(primary_key=True)

    estudiante = models.ForeignKey(
        Estudiante,
        on_delete=models.PROTECT,
        db_column="id_estudiante",
        related_name="matriculas",
    )

    ciclo = models.ForeignKey(
        CicloAcademico,
        on_delete=models.PROTECT,
        db_column="id_ciclo",
        related_name="matriculas",
    )

    numero_matricula = models.CharField(max_length=30, unique=True)
    fecha_matricula = models.DateField()
    estado = models.CharField(max_length=20)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "matricula"

        constraints = (
            models.UniqueConstraint(
                fields=["estudiante", "ciclo"],
                name="uq_matricula_estudiante_ciclo",
            ),
        )

        verbose_name = "Matrícula"
        verbose_name_plural = "Matrículas"

    def __str__(self):
        return self.numero_matricula


class InscripcionCurso(models.Model):
    id_inscripcion = models.BigAutoField(primary_key=True)

    matricula = models.ForeignKey(
        Matricula,
        on_delete=models.PROTECT,
        db_column="id_matricula",
        related_name="inscripciones",
    )

    curso = models.ForeignKey(
        Curso,
        on_delete=models.PROTECT,
        db_column="id_curso",
        related_name="inscripciones",
    )

    fecha_inscripcion = models.DateField()
    estado = models.CharField(max_length=40)
    fecha_cierre = models.DateField(null=True, blank=True)
    motivo_cierre = models.TextField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "inscripcion_curso"

        constraints = (
            models.UniqueConstraint(
                fields=["matricula", "curso"],
                name="uq_inscripcion_matricula_curso",
            ),
        )

        verbose_name = "Inscripción en curso"
        verbose_name_plural = "Inscripciones en cursos"

    def __str__(self):
        return f"{self.matricula} - {self.curso}"


class SesionClase(models.Model):
    NUMEROS_CLASE = (
        (1, "Clase 1"),
        (2, "Clase 2"),
        (3, "Clase 3"),
        (4, "Clase 4"),
        (5, "Clase 5"),
        (6, "Clase 6"),
        (7, "Clase 7 extraordinaria"),
        (8, "Clase 8 extraordinaria"),
    )

    id_sesion = models.BigAutoField(primary_key=True)

    curso = models.ForeignKey(
        Curso,
        on_delete=models.PROTECT,
        db_column="id_curso",
        related_name="sesiones",
    )

    numero_clase = models.SmallIntegerField(
        choices=NUMEROS_CLASE,
        verbose_name="Número de clase",
    )

    ESTADOS_SESION = (
        ("PROGRAMADA", "Programada"),
        ("IMPARTIDA", "Impartida"),
        ("SUSPENDIDA", "Suspendida"),
        ("CANCELADA", "Cancelada"),
    )

    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    estado = models.CharField(max_length=20, choices=ESTADOS_SESION)
    es_extraordinaria = models.BooleanField(
        default=False,
        verbose_name="¿Es extraordinaria?",
    )

    motivo_extension = models.TextField(
        null=True,
        blank=True,
        verbose_name="Motivo de la extensión",
    )

    usuario_autoriza = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="id_usuario_autoriza",
        null=True,
        blank=True,
        related_name="sesiones_extraordinarias_autorizadas",
        verbose_name="Directora que autoriza",
    )

    fecha_autorizacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de autorización",
    )

    observaciones = models.TextField(null=True, blank=True)

    def clean(self):
        super().clean()
        errores = {}

        if self.numero_clase is not None:
            if not 1 <= self.numero_clase <= 8:
                errores["numero_clase"] = "El número de clase debe estar entre 1 y 8."

            elif self.numero_clase <= 6:
                self.es_extraordinaria = False

            else:
                self.es_extraordinaria = True

                if not self.motivo_extension or not self.motivo_extension.strip():
                    errores["motivo_extension"] = (
                        "Debe indicar el motivo de la clase extraordinaria."
                    )

                usuario = self.usuario_autoriza
                if usuario is None:
                    errores["usuario_autoriza"] = (
                        "La clase extraordinaria debe ser autorizada por la directora."
                    )
                else:
                    if usuario.rol != "DIRECTORA":
                        errores["usuario_autoriza"] = (
                            "Solamente una usuaria con rol DIRECTORA "
                            "puede autorizar esta clase."
                        )

                if self.fecha_autorizacion is None:
                    errores["fecha_autorizacion"] = (
                        "Debe registrar la fecha de autorización."
                    )

        if (
            self.hora_inicio is not None
            and self.hora_fin is not None
            and self.hora_fin <= self.hora_inicio
        ):
            errores["hora_fin"] = "La hora final debe ser posterior a la hora inicial."

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        managed = False
        db_table = "sesion_clase"

        constraints = (
            models.UniqueConstraint(
                fields=["curso", "numero_clase"],
                name="uq_sesion_curso_numero_clase",
            ),
        )

        verbose_name = "Sesión de clase"
        verbose_name_plural = "Sesiones de clase"

    def __str__(self):
        tipo = " extraordinaria" if self.es_extraordinaria else ""
        return f"{self.curso} - Clase {self.numero_clase}{tipo}"


class Asistencia(models.Model):
    id_asistencia = models.BigAutoField(primary_key=True)

    ESTADOS_ASISTENCIA = (
        ("PRESENTE", "Presente"),
        ("AUSENTE_JUSTIFICADA", "Ausencia justificada"),
        ("AUSENTE_INJUSTIFICADA", "Ausencia injustificada"),
    )

    inscripcion = models.ForeignKey(
        InscripcionCurso,
        on_delete=models.PROTECT,
        db_column="id_inscripcion",
        related_name="asistencias",
    )

    sesion = models.ForeignKey(
        SesionClase,
        on_delete=models.PROTECT,
        db_column="id_sesion",
        related_name="asistencias",
    )

    estado_asistencia = models.CharField(max_length=30, choices=ESTADOS_ASISTENCIA)
    observaciones = models.TextField(null=True, blank=True)

    def clean(self):
        super().clean()
        errores = {}

        estados_validos = {codigo for codigo, nombre in self.ESTADOS_ASISTENCIA}

        if self.estado_asistencia not in estados_validos:
            errores["estado_asistencia"] = "Seleccione un estado de asistencia válido."

        inscripcion = None
        sesion = None

        if self.__dict__.get("inscripcion_id") is not None:
            inscripcion = self.inscripcion

        if self.__dict__.get("sesion_id") is not None:
            sesion = self.sesion

        if (
            inscripcion is not None
            and sesion is not None
            and inscripcion.curso.pk != sesion.curso.pk
        ):
            errores["sesion"] = (
                "La sesión seleccionada no pertenece al curso de esta inscripción."
            )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()

        with transaction.atomic():
            super().save(*args, **kwargs)

            if self.estado_asistencia == "AUSENTE_INJUSTIFICADA":
                cantidad_ausencias = Asistencia.objects.filter(
                    inscripcion=self.inscripcion,
                    estado_asistencia="AUSENTE_INJUSTIFICADA",
                ).count()

                if cantidad_ausencias >= 2:
                    InscripcionCurso.objects.filter(pk=self.inscripcion.pk).exclude(
                        estado="REPROBADA_POR_INASISTENCIA"
                    ).update(
                        estado="REPROBADA_POR_INASISTENCIA",
                        fecha_cierre=self.sesion.fecha,
                        motivo_cierre=("Acumuló dos ausencias injustificadas."),
                    )

    class Meta:
        managed = False
        db_table = "asistencia"

        constraints = (
            models.UniqueConstraint(
                fields=["inscripcion", "sesion"],
                name="uq_asistencia_inscripcion_sesion",
            ),
        )

        verbose_name = "Asistencia"
        verbose_name_plural = "Asistencias"

    def __str__(self):
        return (
            f"{self.inscripcion} - "
            f"Clase {self.sesion.numero_clase}: "
            f"{self.estado_asistencia}"
        )


class Calificacion(models.Model):
    id_calificacion = models.BigAutoField(primary_key=True)

    ESTADOS_CALIFICACION = (
        ("PENDIENTE", "Pendiente"),
        ("APROBADA", "Aprobada"),
        ("REPROBADA_ACADEMICAMENTE", "Reprobada académicamente"),
    )

    inscripcion = models.OneToOneField(
        InscripcionCurso,
        on_delete=models.PROTECT,
        db_column="id_inscripcion",
        related_name="calificacion",
    )

    nota_final = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    fecha_registro = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=30, choices=ESTADOS_CALIFICACION)
    observaciones = models.TextField(null=True, blank=True)

    def clean(self):
        super().clean()
        errores = {}

        if self.nota_final is not None and (
            self.nota_final < 0 or self.nota_final > 100
        ):
            errores["nota_final"] = "La nota final debe estar entre 0 y 100."

        inscripcion = None

        if self.__dict__.get("inscripcion_id") is not None:
            inscripcion = self.inscripcion

        if (
            inscripcion is not None
            and inscripcion.estado == "REPROBADA_POR_INASISTENCIA"
            and self.nota_final is not None
        ):
            errores["nota_final"] = (
                "No se puede registrar una nota porque el estudiante "
                "fue excluido por inasistencia."
            )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        if self.nota_final is None:
            self.estado = "PENDIENTE"
        elif self.nota_final >= 70:
            self.estado = "APROBADA"
        else:
            self.estado = "REPROBADA_ACADEMICAMENTE"

        if self.fecha_registro is None:
            self.fecha_registro = timezone.now()

        self.full_clean()

        with transaction.atomic():
            super().save(*args, **kwargs)

            if self.nota_final is not None:
                if self.estado == "APROBADA":
                    motivo = "Materia aprobada con nota final."
                else:
                    motivo = "Materia reprobada académicamente."

                InscripcionCurso.objects.filter(pk=self.inscripcion.pk).exclude(
                    estado="REPROBADA_POR_INASISTENCIA"
                ).update(
                    estado=self.estado,
                    fecha_cierre=timezone.localdate(),
                    motivo_cierre=motivo,
                )

    class Meta:
        managed = False
        db_table = "calificacion"
        verbose_name = "Calificación"
        verbose_name_plural = "Calificaciones"

    def __str__(self):
        nota = self.nota_final if self.nota_final is not None else "Pendiente"
        return f"{self.inscripcion} - Nota: {nota}"
