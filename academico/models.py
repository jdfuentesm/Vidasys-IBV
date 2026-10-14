from django.conf import settings
from django.db import models


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
    id_materia = models.BigAutoField(primary_key=True)
    codigo_materia = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    estado = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "materia"
        verbose_name = "Materia"
        verbose_name_plural = "Materias"

    def __str__(self):
        return f"{self.codigo_materia} - {self.nombre}"


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
    estado = models.CharField(max_length=20)

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
    id_sesion = models.BigAutoField(primary_key=True)

    curso = models.ForeignKey(
        Curso,
        on_delete=models.PROTECT,
        db_column="id_curso",
        related_name="sesiones",
    )

    numero_clase = models.SmallIntegerField()
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    estado = models.CharField(max_length=20)
    observaciones = models.TextField(null=True, blank=True)

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
        return f"{self.curso} - Clase {self.numero_clase}"


class Asistencia(models.Model):
    id_asistencia = models.BigAutoField(primary_key=True)

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

    estado_asistencia = models.CharField(max_length=30)
    observaciones = models.TextField(null=True, blank=True)

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
    estado = models.CharField(max_length=20)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "calificacion"
        verbose_name = "Calificación"
        verbose_name_plural = "Calificaciones"

    def __str__(self):
        nota = self.nota_final if self.nota_final is not None else "Pendiente"
        return f"{self.inscripcion} - Nota: {nota}"
