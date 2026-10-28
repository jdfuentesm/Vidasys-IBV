from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ConceptoCobro(models.Model):
    id_concepto = models.BigAutoField(primary_key=True)

    nombre = models.CharField(
        max_length=100,
        unique=True,
    )

    descripcion = models.TextField(
        null=True,
        blank=True,
    )

    permite_abonos = models.BooleanField(
        default=False,
    )

    estado = models.CharField(
        max_length=20,
    )

    class Meta:
        managed = False
        db_table = "concepto_cobro"
        verbose_name = "Concepto de cobro"
        verbose_name_plural = "Conceptos de cobro"

    def __str__(self):
        return self.nombre


class Obligacion(models.Model):
    id_obligacion = models.BigAutoField(primary_key=True)

    matricula = models.ForeignKey(
        "academico.Matricula",
        on_delete=models.PROTECT,
        db_column="id_matricula",
        related_name="obligaciones",
    )

    concepto = models.ForeignKey(
        ConceptoCobro,
        on_delete=models.PROTECT,
        db_column="id_concepto",
        related_name="obligaciones",
    )

    descripcion = models.CharField(max_length=200)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()

    monto_original = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    monto_descuento = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    #  monto_final = models.DecimalField(
    #      max_digits=10,
    #      decimal_places=2,
    #      editable=False,  # This field is calculated based on monto_original and monto_descuento
    # )
    estado = models.CharField(max_length=20)
    observaciones = models.TextField(null=True, blank=True)

    # def save(self, *args, **kwargs):
    # Si la obligación es nueva (no tiene ID), le decimos a Django
    # que no intente guardar el monto_final porque la BD lo calcula.
    #    if not self.pk:
    #       # Esto es un truco para que Django no incluya el campo en el INSERT
    #      self._meta.get_field("monto_final").auto_created = True

    #    super().save(*args, **kwargs)

    # Recargamos la obligación para traer el monto_final calculado por la BD
    #    self.refresh_from_db()

    class Meta:
        managed = False
        db_table = "obligacion"

        constraints = (
            models.UniqueConstraint(
                fields=["matricula", "concepto", "fecha_vencimiento"],
                name="uq_obligacion_matricula_concepto_vencimiento",
            ),
        )

        verbose_name = "Obligación"
        verbose_name_plural = "Obligaciones"

    @property
    def monto_final(self):
        if self.monto_original is None:
            return None
        return self.monto_original - (self.monto_descuento or Decimal("0.00"))

    def clean(self):
        errores = {}

        if self.monto_original is not None and self.monto_original <= Decimal("0.00"):
            errores["monto_original"] = "El monto original debe ser mayor que cero."

        if self.monto_descuento is not None and self.monto_descuento < Decimal("0.00"):
            errores["monto_descuento"] = "El descuento no puede ser negativo."

        if (
            self.monto_original is not None
            and self.monto_descuento is not None
            and self.monto_descuento > self.monto_original
        ):
            errores["monto_descuento"] = (
                "El descuento no puede superar el monto original."
            )

        if (
            self.monto_original is not None
            and self.monto_descuento is not None
            and self.monto_final is not None
        ):
            monto_esperado = self.monto_original - self.monto_descuento

            if self.monto_final != monto_esperado:
                errores["monto_final"] = f"El monto final debe ser {monto_esperado}."

        if (
            self.fecha_emision
            and self.fecha_vencimiento
            and self.fecha_vencimiento < self.fecha_emision
        ):
            errores["fecha_vencimiento"] = (
                "La fecha de vencimiento no puede ser anterior a la fecha de emisión."
            )

        if errores:
            raise ValidationError(errores)

    def actualizar_estado(self):
        # Sumamos todos los pagos aplicados a esta obligación
        total_pagado = sum(
            detalle.monto_aplicado
            for detalle in DetallePago.objects.filter(obligacion_id=self.pk)
        )

        # 🔥 EL TRUCO: Le preguntamos a la base de datos cuánto es el monto_final
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT monto_final FROM obligacion WHERE id_obligacion = %s", [self.pk]
            )
            monto_final_bd = cursor.fetchone()[0]

        if total_pagado == 0:
            self.estado = "PENDIENTE"
        elif total_pagado < monto_final_bd:  # <-- Usamos el valor de la BD
            self.estado = "PARCIAL"
        else:
            self.estado = "PAGADA"

        # Guardamos solo el estado
        self.save(update_fields=["estado"])

    def __str__(self):
        return f"{self.matricula} - {self.concepto} - {self.fecha_vencimiento}"


class Pago(models.Model):
    id_pago = models.BigAutoField(primary_key=True)

    estudiante = models.ForeignKey(
        "academico.Estudiante",
        on_delete=models.PROTECT,
        db_column="id_estudiante",
        related_name="pagos",
    )

    usuario = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario",
        related_name="pagos_registrados",
    )

    numero_recibo = models.CharField(
        max_length=30,
        unique=True,
    )

    fecha_pago = models.DateTimeField()

    monto_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    metodo_pago = models.CharField(max_length=20)

    referencia = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=20)

    observaciones = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "pago"
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"

    def clean(self):
        errores = {}

        if self.monto_total is not None and self.monto_total <= Decimal("0.00"):
            errores["monto_total"] = "El monto total del pago debe ser mayor que cero."

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"{self.numero_recibo} - {self.estudiante}"


class DetallePago(models.Model):
    id_detalle_pago = models.BigAutoField(primary_key=True)

    pago = models.ForeignKey(
        Pago,
        on_delete=models.PROTECT,
        db_column="id_pago",
        related_name="detalles",
    )

    obligacion = models.ForeignKey(
        Obligacion,
        on_delete=models.PROTECT,
        db_column="id_obligacion",
        related_name="detalles_pago",
    )

    monto_aplicado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        managed = False
        db_table = "detalle_pago"
        verbose_name = "Detalle de pago"
        verbose_name_plural = "Detalles de pago"
        constraints = (
            models.UniqueConstraint(
                fields=["pago", "obligacion"],
                name="uq_detalle_pago_obligacion",
            ),
        )

    def clean(self):
        errores = {}

        if self.monto_aplicado is not None and self.monto_aplicado <= Decimal("0.00"):
            errores["monto_aplicado"] = "El monto aplicado debe ser mayor que cero."

        if (
            self.monto_aplicado is not None
            and hasattr(self, "obligacion")
            and self.obligacion.monto_final is not None
            and self.monto_aplicado > self.obligacion.monto_final
        ):
            errores["monto_aplicado"] = (
                "El monto aplicado no puede superar el monto final de la obligación."
            )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Guardamos el detalle de pago primero
        self.obligacion.actualizar_estado()  # Luego actualizamos el estado de la obligación asociada

    def delete(self, *args, **kwargs):
        obligacion = self.obligacion
        super().delete(*args, **kwargs)  # Eliminamos el detalle de pago primero
        obligacion.actualizar_estado()  # Luego actualizamos el estado de la obligación asociada

    def __str__(self):
        return f"{self.pago.numero_recibo} - {self.obligacion}"


class Beca(models.Model):
    id_beca = models.BigAutoField(primary_key=True)

    matricula = models.ForeignKey(
        "academico.Matricula",
        on_delete=models.PROTECT,
        db_column="id_matricula",
        related_name="becas",
    )

    usuario_autoriza = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_autoriza",
        related_name="becas_autorizadas",
    )

    porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    fecha_aprobacion = models.DateField()
    fecha_inicio = models.DateField()

    fecha_fin = models.DateField(
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=20)

    observaciones = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "beca"
        verbose_name = "Beca"
        verbose_name_plural = "Becas"

    def clean(self):
        errores = {}

        porcentajes_permitidos = {
            Decimal("50.00"),
            Decimal("100.00"),
        }

        if self.porcentaje not in porcentajes_permitidos:
            errores["porcentaje"] = "La beca solamente puede ser del 50% o del 100%."

        if self.fecha_fin and self.fecha_inicio and self.fecha_fin < self.fecha_inicio:
            errores["fecha_fin"] = (
                "La fecha final no puede ser anterior a la fecha de inicio."
            )

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"{self.matricula} - {self.porcentaje}%"


class AplicacionBeca(models.Model):
    id_aplicacion_beca = models.BigAutoField(primary_key=True)

    beca = models.ForeignKey(
        Beca,
        on_delete=models.PROTECT,
        db_column="id_beca",
        related_name="aplicaciones",
    )

    obligacion = models.ForeignKey(
        Obligacion,
        on_delete=models.PROTECT,
        db_column="id_obligacion",
        related_name="aplicaciones_beca",
    )

    monto_aplicado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    fecha_aplicacion = models.DateTimeField()

    estado = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "aplicacion_beca"
        verbose_name = "Aplicación de beca"
        verbose_name_plural = "Aplicaciones de becas"
        constraints = (
            models.UniqueConstraint(
                fields=["beca", "obligacion"],
                name="uq_aplicacion_beca_obligacion",
            ),
        )

    def clean(self):
        errores = {}

        conceptos_permitidos = {
            "MATRICULA",
            "MENSUALIDAD",
        }

        if self.monto_aplicado is not None and (self.monto_aplicado <= Decimal("0.00")):
            errores["monto_aplicado"] = "El monto aplicado debe ser mayor que cero."

        if hasattr(self, "obligacion"):
            nombre_concepto = self.obligacion.concepto.nombre.strip().upper()

            if nombre_concepto not in conceptos_permitidos:
                errores["obligacion"] = (
                    "Las becas solamente pueden aplicarse a matrícula o mensualidades."
                )

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"{self.beca} - {self.obligacion}"


class ConvenioPago(models.Model):
    id_convenio = models.BigAutoField(primary_key=True)

    estudiante = models.ForeignKey(
        "academico.Estudiante",
        on_delete=models.PROTECT,
        db_column="id_estudiante",
        related_name="convenios_pago",
    )

    usuario_autoriza = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_autoriza",
        related_name="convenios_autorizados",
    )

    usuario_cancela = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_cancela",
        related_name="convenios_cancelados",
        null=True,
        blank=True,
    )

    fecha_convenio = models.DateField()

    monto_convenido = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    numero_cuotas = models.SmallIntegerField()

    estado = models.CharField(max_length=20)

    fecha_actualizacion = models.DateTimeField(
        null=True,
        blank=True,
    )

    fecha_cancelacion = models.DateTimeField(
        null=True,
        blank=True,
    )

    motivo_cancelacion = models.TextField(
        null=True,
        blank=True,
    )

    observaciones = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "convenio_pago"
        verbose_name = "Convenio de pago"
        verbose_name_plural = "Convenios de pago"

    def clean(self):
        errores = {}

        if self.monto_convenido is not None and self.monto_convenido <= Decimal("0.00"):
            errores["monto_convenido"] = "El monto convenido debe ser mayor que cero."

        if self.numero_cuotas is not None and self.numero_cuotas <= 0:
            errores["numero_cuotas"] = "El convenio debe contener al menos una cuota."

        if self.estado == "CANCELADO":
            if self.usuario_cancela is None:
                errores["usuario_cancela"] = "Debe indicar quién canceló el convenio."

            if not self.fecha_cancelacion:
                errores["fecha_cancelacion"] = "Debe registrar la fecha de cancelación."

            if not self.motivo_cancelacion:
                errores["motivo_cancelacion"] = (
                    "Debe indicar el motivo de la cancelación."
                )

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"Convenio {self.id_convenio} - {self.estudiante}"


class ConvenioObligacion(models.Model):
    id_convenio_obligacion = models.BigAutoField(primary_key=True)

    convenio = models.ForeignKey(
        ConvenioPago,
        on_delete=models.PROTECT,
        db_column="id_convenio",
        related_name="obligaciones_incluidas",
    )

    obligacion = models.ForeignKey(
        Obligacion,
        on_delete=models.PROTECT,
        db_column="id_obligacion",
        related_name="convenios",
    )

    saldo_incluido = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        managed = False
        db_table = "convenio_obligacion"
        verbose_name = "Obligación del convenio"
        verbose_name_plural = "Obligaciones del convenio"
        constraints = (
            models.UniqueConstraint(
                fields=["convenio", "obligacion"],
                name="uq_convenio_obligacion",
            ),
        )

    def clean(self):
        errores = {}

        if self.saldo_incluido is not None and self.saldo_incluido <= Decimal("0.00"):
            errores["saldo_incluido"] = "El saldo incluido debe ser mayor que cero."

        if hasattr(self, "obligacion"):
            if self.obligacion.estado == "PAGADA":
                errores["obligacion"] = (
                    "Una obligación pagada no puede incluirse en un convenio."
                )

            if (
                self.obligacion.fecha_vencimiento
                and self.obligacion.fecha_vencimiento >= timezone.localdate()
            ):
                errores["obligacion"] = (
                    "El convenio solamente puede incluir obligaciones vencidas."
                )

        if hasattr(self, "convenio") and hasattr(self, "obligacion"):
            estudiante_convenio = self.convenio.estudiante.pk
            estudiante_obligacion = self.obligacion.matricula.estudiante.pk

            if estudiante_convenio != estudiante_obligacion:
                errores["obligacion"] = "La obligación pertenece a otro estudiante."

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"{self.convenio} - {self.obligacion}"


class CuotaConvenio(models.Model):
    id_cuota = models.BigAutoField(primary_key=True)

    convenio = models.ForeignKey(
        ConvenioPago,
        on_delete=models.PROTECT,
        db_column="id_convenio",
        related_name="cuotas",
    )

    numero_cuota = models.SmallIntegerField()

    fecha_vencimiento = models.DateField()

    monto_cuota = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    estado = models.CharField(max_length=20)

    def clean(self):
        super().clean()
        errores = {}

        if self.numero_cuota is not None and self.numero_cuota <= 0:
            errores["numero_cuota"] = "El número de cuota debe ser mayor que cero."

        if self.monto_cuota is not None and self.monto_cuota <= 0:
            errores["monto_cuota"] = "El monto de la cuota debe ser mayor que cero."

        convenio = None

        if self.__dict__.get("convenio_id") is not None:
            convenio = self.convenio

        if (
            convenio is not None
            and self.numero_cuota is not None
            and convenio.numero_cuotas is not None
            and self.numero_cuota > convenio.numero_cuotas
        ):
            errores["numero_cuota"] = (
                "El número de cuota supera la cantidad establecida en el convenio."
            )

        if (
            convenio is not None
            and self.fecha_vencimiento
            and convenio.fecha_convenio
            and self.fecha_vencimiento < convenio.fecha_convenio
        ):
            errores["fecha_vencimiento"] = (
                "La fecha de vencimiento no puede ser anterior a la fecha del convenio."
            )

        if errores:
            raise ValidationError(errores)

    class Meta:
        managed = False
        db_table = "cuota_convenio"
        verbose_name = "Cuota de convenio"
        verbose_name_plural = "Cuotas de convenios"
        constraints = (
            models.UniqueConstraint(
                fields=["convenio", "numero_cuota"],
                name="uq_convenio_numero_cuota",
            ),
        )

    def __str__(self):
        return f"{self.convenio} - Cuota {self.numero_cuota}"


class AplicacionPagoCuota(models.Model):
    id_aplicacion_pago_cuota = models.BigAutoField(primary_key=True)

    pago = models.ForeignKey(
        Pago,
        on_delete=models.PROTECT,
        db_column="id_pago",
        related_name="aplicaciones_cuotas",
    )

    cuota = models.ForeignKey(
        CuotaConvenio,
        on_delete=models.PROTECT,
        db_column="id_cuota",
        related_name="aplicaciones_pago",
    )

    monto_aplicado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    def clean(self):
        super().clean()
        errores = {}

        if self.monto_aplicado is not None and self.monto_aplicado <= 0:
            errores["monto_aplicado"] = "El monto aplicado debe ser mayor que cero."

        cuota = None
        pago = None

        if self.__dict__.get("cuota_id") is not None:
            cuota = self.cuota

        if self.__dict__.get("pago_id") is not None:
            pago = self.pago

        if (
            cuota is not None
            and self.monto_aplicado is not None
            and self.monto_aplicado > cuota.monto_cuota
        ):
            errores["monto_aplicado"] = (
                "El monto aplicado no puede superar el monto de la cuota."
            )

        if (
            pago is not None
            and self.monto_aplicado is not None
            and self.monto_aplicado > pago.monto_total
        ):
            errores["monto_aplicado"] = (
                "El monto aplicado no puede superar el total del pago."
            )

        if errores:
            raise ValidationError(errores)

    class Meta:
        managed = False
        db_table = "aplicacion_pago_cuota"
        verbose_name = "Aplicación de pago a cuota"
        verbose_name_plural = "Aplicaciones de pagos a cuotas"
        constraints = (
            models.UniqueConstraint(
                fields=["pago", "cuota"],
                name="uq_pago_cuota",
            ),
        )

    def __str__(self):
        return f"{self.pago.numero_recibo} - Cuota {self.cuota.numero_cuota}"


class CategoriaIngreso(models.Model):
    id_categoria_ingreso = models.BigAutoField(primary_key=True)

    nombre = models.CharField(
        max_length=100,
        unique=True,
    )

    descripcion = models.TextField(
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "categoria_ingreso"
        verbose_name = "Categoría de ingreso"
        verbose_name_plural = "Categorías de ingresos"

    def __str__(self):
        return self.nombre


class Ingreso(models.Model):
    id_ingreso = models.BigAutoField(primary_key=True)

    categoria_ingreso = models.ForeignKey(
        CategoriaIngreso,
        on_delete=models.PROTECT,
        db_column="id_categoria_ingreso",
        related_name="ingresos",
    )

    usuario_registra = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_registra",
        related_name="ingresos_registrados",
    )

    usuario_anula = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_anula",
        related_name="ingresos_anulados",
        null=True,
        blank=True,
    )

    fecha_ingreso = models.DateTimeField()

    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    metodo_pago = models.CharField(max_length=20)

    referencia = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=20)

    fecha_anulacion = models.DateTimeField(
        null=True,
        blank=True,
    )

    motivo_anulacion = models.TextField(
        null=True,
        blank=True,
    )

    observaciones = models.TextField(
        null=True,
        blank=True,
    )

    fecha_creacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "ingreso"
        verbose_name = "Ingreso"
        verbose_name_plural = "Ingresos"

    def clean(self):
        errores = {}

        if self.monto is not None and self.monto <= Decimal("0.00"):
            errores["monto"] = "El monto debe ser mayor que cero."

        if self.estado == "ANULADO":
            if self.usuario_anula is None:
                errores["usuario_anula"] = "Debe indicar quién anuló el ingreso."

            if not self.fecha_anulacion:
                errores["fecha_anulacion"] = "Debe registrar la fecha de anulación."

            if not self.motivo_anulacion:
                errores["motivo_anulacion"] = "Debe indicar el motivo de la anulación."

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"Ingreso {self.id_ingreso} - ${self.monto}"


class CategoriaEgreso(models.Model):
    id_categoria_egreso = models.BigAutoField(primary_key=True)

    nombre = models.CharField(
        max_length=100,
        unique=True,
    )

    descripcion = models.TextField(
        null=True,
        blank=True,
    )

    requiere_autorizacion = models.BooleanField(default=False)

    estado = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "categoria_egreso"
        verbose_name = "Categoría de egreso"
        verbose_name_plural = "Categorías de egresos"

    def __str__(self):
        return self.nombre


class Egreso(models.Model):
    id_egreso = models.BigAutoField(primary_key=True)

    categoria_egreso = models.ForeignKey(
        CategoriaEgreso,
        on_delete=models.PROTECT,
        db_column="id_categoria_egreso",
        related_name="egresos",
    )

    usuario_registra = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_registra",
        related_name="egresos_registrados",
    )

    usuario_autoriza = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_autoriza",
        related_name="egresos_autorizados",
        null=True,
        blank=True,
    )

    usuario_anula = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_anula",
        related_name="egresos_anulados",
        null=True,
        blank=True,
    )

    numero_egreso = models.CharField(
        max_length=30,
        unique=True,
    )

    numero_comprobante = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    tipo_comprobante = models.CharField(max_length=30)

    fecha_egreso = models.DateTimeField()

    concepto = models.CharField(max_length=200)

    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    metodo_pago = models.CharField(max_length=20)

    referencia = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    fecha_autorizacion = models.DateTimeField(
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=30)

    fecha_anulacion = models.DateTimeField(
        null=True,
        blank=True,
    )

    motivo_anulacion = models.TextField(
        null=True,
        blank=True,
    )

    observaciones = models.TextField(
        null=True,
        blank=True,
    )

    fecha_creacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "egreso"
        verbose_name = "Egreso"
        verbose_name_plural = "Egresos"

    def clean(self):
        errores = {}

        if self.monto is not None and self.monto <= Decimal("0.00"):
            errores["monto"] = "El monto debe ser mayor que cero."

        if (
            hasattr(self, "categoria_egreso")
            and self.categoria_egreso.requiere_autorizacion
        ):
            if self.usuario_autoriza is None:
                errores["usuario_autoriza"] = (
                    "Esta categoría requiere autorización de la directora."
                )

            if not self.fecha_autorizacion:
                errores["fecha_autorizacion"] = (
                    "Debe registrar la fecha de autorización."
                )

        if self.estado == "ANULADO":
            if self.usuario_anula is None:
                errores["usuario_anula"] = "Debe indicar quién anuló el egreso."

            if not self.fecha_anulacion:
                errores["fecha_anulacion"] = "Debe registrar la fecha de anulación."

            if not self.motivo_anulacion:
                errores["motivo_anulacion"] = "Debe indicar el motivo de la anulación."

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"{self.numero_egreso} - {self.concepto}"


class Donante(models.Model):
    id_donante = models.BigAutoField(primary_key=True)

    tipo = models.CharField(max_length=20)
    nombre_completo = models.CharField(max_length=150)

    documento_identidad = models.CharField(
        max_length=50,
        null=True,
        blank=True,
    )

    correo = models.CharField(
        max_length=150,
        null=True,
        blank=True,
    )

    telefono = models.CharField(
        max_length=25,
        null=True,
        blank=True,
    )

    pais = models.CharField(
        max_length=80,
        null=True,
        blank=True,
    )

    direccion = models.TextField(
        null=True,
        blank=True,
    )

    es_anonimo = models.BooleanField(default=False)

    notas = models.TextField(
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=20)
    fecha_registro = models.DateTimeField()
    fecha_actualizacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "donante"
        verbose_name = "Donante"
        verbose_name_plural = "Donantes"

    def __str__(self):
        if self.es_anonimo:
            return "Donante anónimo"
        return self.nombre_completo


class Padrinazgo(models.Model):
    id_padrinazgo = models.BigAutoField(primary_key=True)

    donante = models.ForeignKey(
        Donante,
        on_delete=models.PROTECT,
        db_column="id_donante",
        related_name="padrinazgos",
    )

    matricula = models.ForeignKey(
        "academico.Matricula",
        on_delete=models.PROTECT,
        db_column="id_matricula",
        related_name="padrinazgos",
    )

    fecha_inicio = models.DateField()

    fecha_fin = models.DateField(
        null=True,
        blank=True,
    )

    monto_mensual = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    porcentaje_cobertura = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=20)

    observaciones = models.TextField(
        null=True,
        blank=True,
    )

    fecha_registro = models.DateTimeField()
    fecha_actualizacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "padrinazgo"
        verbose_name = "Padrinazgo"
        verbose_name_plural = "Padrinazgos"

    def clean(self):
        super().clean()
        errores = {}

        tiene_monto = self.monto_mensual is not None
        tiene_porcentaje = self.porcentaje_cobertura is not None

        if tiene_monto == tiene_porcentaje:
            errores["__all__"] = (
                "Debe indicar un monto mensual o un porcentaje de cobertura, "
                "pero no ambos."
            )

        if self.monto_mensual is not None and self.monto_mensual <= Decimal("0.00"):
            errores["monto_mensual"] = "El monto mensual debe ser mayor que cero."

        if self.porcentaje_cobertura is not None and not (
            Decimal("0.00") < self.porcentaje_cobertura <= Decimal("100.00")
        ):
            errores["porcentaje_cobertura"] = (
                "El porcentaje debe ser mayor que 0 y menor o igual que 100."
            )

        if self.fecha_fin and self.fecha_inicio and self.fecha_fin < self.fecha_inicio:
            errores["fecha_fin"] = (
                "La fecha final no puede ser anterior a la fecha de inicio."
            )

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"{self.donante} - {self.matricula}"


class Donacion(models.Model):
    id_donacion = models.BigAutoField(primary_key=True)

    donante = models.ForeignKey(
        Donante,
        on_delete=models.PROTECT,
        db_column="id_donante",
        related_name="donaciones",
    )

    padrinazgo = models.ForeignKey(
        Padrinazgo,
        on_delete=models.PROTECT,
        db_column="id_padrinazgo",
        related_name="donaciones",
        null=True,
        blank=True,
    )

    obligacion = models.ForeignKey(
        Obligacion,
        on_delete=models.PROTECT,
        db_column="id_obligacion",
        related_name="donaciones",
        null=True,
        blank=True,
    )

    ingreso = models.OneToOneField(
        Ingreso,
        on_delete=models.PROTECT,
        db_column="id_ingreso",
        related_name="donacion",
        null=True,
        blank=True,
    )

    usuario_registra = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_registra",
        related_name="donaciones_registradas",
    )

    usuario_confirma = models.ForeignKey(
        "core.Usuario",
        on_delete=models.PROTECT,
        db_column="id_usuario_confirma",
        related_name="donaciones_confirmadas",
        null=True,
        blank=True,
    )

    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    fecha_compromiso = models.DateField()

    fecha_ingreso = models.DateField(
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=30)

    metodo_pago = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    referencia = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    observaciones = models.TextField(
        null=True,
        blank=True,
    )

    fecha_registro = models.DateTimeField()
    fecha_actualizacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "donacion"
        verbose_name = "Donación"
        verbose_name_plural = "Donaciones"

    def __str__(self):
        return f"Donación {self.id_donacion} - {self.donante}"
