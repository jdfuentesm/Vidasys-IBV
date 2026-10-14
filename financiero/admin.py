from django.contrib import admin

from .models import (
    AplicacionBeca,
    AplicacionPagoCuota,
    Beca,
    CategoriaEgreso,
    CategoriaIngreso,
    ConceptoCobro,
    ConvenioObligacion,
    ConvenioPago,
    CuotaConvenio,
    DetallePago,
    Donacion,
    Donante,
    Egreso,
    Ingreso,
    Obligacion,
    Padrinazgo,
    Pago,
)


class NoEliminarAdminMixin(admin.ModelAdmin):
    """
    Impide eliminar registros financieros desde el panel administrativo.
    Los errores deben corregirse mediante estados o anulaciones.
    """

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


@admin.register(ConceptoCobro)
class ConceptoCobroAdmin(admin.ModelAdmin):
    list_display = (
        "id_concepto",
        "nombre",
        "permite_abonos",
        "estado",
    )
    list_filter = (
        "permite_abonos",
        "estado",
    )
    search_fields = (
        "nombre",
        "descripcion",
    )
    ordering = ("nombre",)


@admin.register(CategoriaIngreso)
class CategoriaIngresoAdmin(admin.ModelAdmin):
    list_display = (
        "id_categoria_ingreso",
        "nombre",
        "estado",
    )
    list_filter = ("estado",)
    search_fields = (
        "nombre",
        "descripcion",
    )
    ordering = ("nombre",)


@admin.register(CategoriaEgreso)
class CategoriaEgresoAdmin(admin.ModelAdmin):
    list_display = (
        "id_categoria_egreso",
        "nombre",
        "requiere_autorizacion",
        "estado",
    )
    list_filter = (
        "requiere_autorizacion",
        "estado",
    )
    search_fields = (
        "nombre",
        "descripcion",
    )
    ordering = ("nombre",)


@admin.register(Obligacion)
class ObligacionAdmin(NoEliminarAdminMixin):
    list_display = (
        "id_obligacion",
        "matricula",
        "concepto",
        "fecha_vencimiento",
        "monto_final",
        "estado",
    )
    list_filter = (
        "estado",
        "concepto",
        "fecha_vencimiento",
    )
    search_fields = (
        "descripcion",
        "matricula__numero_matricula",
        "matricula__estudiante__codigo_estudiante",
        "matricula__estudiante__nombres",
        "matricula__estudiante__apellidos",
    )
    raw_id_fields = (
        "matricula",
        "concepto",
    )
    ordering = (
        "-fecha_vencimiento",
        "-id_obligacion",
    )


class DetallePagoInline(admin.TabularInline):
    model = DetallePago
    extra = 0
    can_delete = False
    raw_id_fields = ("obligacion",)
    fields = (
        "obligacion",
        "monto_aplicado",
    )


@admin.register(Pago)
class PagoAdmin(NoEliminarAdminMixin):
    list_display = (
        "numero_recibo",
        "estudiante",
        "fecha_pago",
        "monto_total",
        "metodo_pago",
        "estado",
    )
    list_filter = (
        "estado",
        "metodo_pago",
        "fecha_pago",
    )
    search_fields = (
        "numero_recibo",
        "estudiante__codigo_estudiante",
        "estudiante__nombres",
        "estudiante__apellidos",
        "referencia",
    )
    raw_id_fields = (
        "estudiante",
        "usuario",
    )
    ordering = (
        "-fecha_pago",
        "-id_pago",
    )
    date_hierarchy = "fecha_pago"
    inlines = (DetallePagoInline,)


class AplicacionBecaInline(admin.TabularInline):
    model = AplicacionBeca
    extra = 0
    can_delete = False
    raw_id_fields = ("obligacion",)
    fields = (
        "obligacion",
        "monto_aplicado",
        "fecha_aplicacion",
        "estado",
    )


@admin.register(Beca)
class BecaAdmin(NoEliminarAdminMixin):
    list_display = (
        "id_beca",
        "matricula",
        "porcentaje",
        "fecha_inicio",
        "fecha_fin",
        "estado",
        "usuario_autoriza",
    )
    list_filter = (
        "estado",
        "porcentaje",
        "fecha_inicio",
    )
    search_fields = (
        "matricula__numero_matricula",
        "matricula__estudiante__codigo_estudiante",
        "matricula__estudiante__nombres",
        "matricula__estudiante__apellidos",
        "observaciones",
    )
    raw_id_fields = (
        "matricula",
        "usuario_autoriza",
    )
    ordering = (
        "-fecha_aprobacion",
        "-id_beca",
    )
    date_hierarchy = "fecha_aprobacion"
    inlines = (AplicacionBecaInline,)


class ConvenioObligacionInline(admin.TabularInline):
    model = ConvenioObligacion
    extra = 0
    can_delete = False
    raw_id_fields = ("obligacion",)
    fields = (
        "obligacion",
        "saldo_incluido",
    )


class CuotaConvenioInline(admin.TabularInline):
    model = CuotaConvenio
    extra = 0
    can_delete = False
    fields = (
        "numero_cuota",
        "fecha_vencimiento",
        "monto_cuota",
        "estado",
    )
    ordering = ("numero_cuota",)


@admin.register(ConvenioPago)
class ConvenioPagoAdmin(NoEliminarAdminMixin):
    list_display = (
        "id_convenio",
        "estudiante",
        "fecha_convenio",
        "monto_convenido",
        "numero_cuotas",
        "estado",
        "usuario_autoriza",
    )
    list_filter = (
        "estado",
        "fecha_convenio",
        "numero_cuotas",
    )
    search_fields = (
        "estudiante__codigo_estudiante",
        "estudiante__nombres",
        "estudiante__apellidos",
        "observaciones",
        "motivo_cancelacion",
    )
    raw_id_fields = (
        "estudiante",
        "usuario_autoriza",
        "usuario_cancela",
    )
    ordering = (
        "-fecha_convenio",
        "-id_convenio",
    )
    date_hierarchy = "fecha_convenio"
    inlines = (
        ConvenioObligacionInline,
        CuotaConvenioInline,
    )


@admin.register(AplicacionPagoCuota)
class AplicacionPagoCuotaAdmin(NoEliminarAdminMixin):
    list_display = (
        "id_aplicacion_pago_cuota",
        "pago",
        "cuota",
        "monto_aplicado",
    )
    search_fields = (
        "pago__numero_recibo",
        "cuota__convenio__estudiante__codigo_estudiante",
        "cuota__convenio__estudiante__nombres",
        "cuota__convenio__estudiante__apellidos",
    )
    raw_id_fields = (
        "pago",
        "cuota",
    )
    ordering = ("-id_aplicacion_pago_cuota",)


@admin.register(Ingreso)
class IngresoAdmin(NoEliminarAdminMixin):
    list_display = (
        "id_ingreso",
        "categoria_ingreso",
        "fecha_ingreso",
        "monto",
        "metodo_pago",
        "estado",
        "usuario_registra",
    )
    list_filter = (
        "estado",
        "categoria_ingreso",
        "metodo_pago",
        "fecha_ingreso",
    )
    search_fields = (
        "referencia",
        "observaciones",
        "motivo_anulacion",
        "usuario_registra__numero_usuario",
    )
    raw_id_fields = (
        "categoria_ingreso",
        "usuario_registra",
        "usuario_anula",
    )
    ordering = (
        "-fecha_ingreso",
        "-id_ingreso",
    )
    date_hierarchy = "fecha_ingreso"


@admin.register(Egreso)
class EgresoAdmin(NoEliminarAdminMixin):
    list_display = (
        "numero_egreso",
        "categoria_egreso",
        "fecha_egreso",
        "concepto",
        "monto",
        "estado",
        "usuario_registra",
        "usuario_autoriza",
    )
    list_filter = (
        "estado",
        "categoria_egreso",
        "metodo_pago",
        "fecha_egreso",
    )
    search_fields = (
        "numero_egreso",
        "numero_comprobante",
        "concepto",
        "referencia",
        "observaciones",
        "motivo_anulacion",
    )
    raw_id_fields = (
        "categoria_egreso",
        "usuario_registra",
        "usuario_autoriza",
        "usuario_anula",
    )
    ordering = (
        "-fecha_egreso",
        "-id_egreso",
    )
    date_hierarchy = "fecha_egreso"


@admin.register(Donante)
class DonanteAdmin(NoEliminarAdminMixin):
    list_display = (
        "id_donante",
        "nombre_completo",
        "tipo",
        "telefono",
        "pais",
        "es_anonimo",
        "estado",
    )
    list_filter = (
        "tipo",
        "es_anonimo",
        "estado",
        "pais",
    )
    search_fields = (
        "nombre_completo",
        "documento_identidad",
        "correo",
        "telefono",
    )
    ordering = ("nombre_completo",)


class DonacionInline(admin.TabularInline):
    model = Donacion
    extra = 0
    can_delete = False
    raw_id_fields = (
        "donante",
        "obligacion",
        "ingreso",
        "usuario_registra",
        "usuario_confirma",
    )
    fields = (
        "donante",
        "obligacion",
        "monto",
        "fecha_compromiso",
        "fecha_ingreso",
        "estado",
    )


@admin.register(Padrinazgo)
class PadrinazgoAdmin(NoEliminarAdminMixin):
    list_display = (
        "id_padrinazgo",
        "donante",
        "matricula",
        "fecha_inicio",
        "fecha_fin",
        "monto_mensual",
        "porcentaje_cobertura",
        "estado",
    )
    list_filter = (
        "estado",
        "fecha_inicio",
        "fecha_fin",
    )
    search_fields = (
        "donante__nombre_completo",
        "matricula__numero_matricula",
        "matricula__estudiante__codigo_estudiante",
        "matricula__estudiante__nombres",
        "matricula__estudiante__apellidos",
    )
    raw_id_fields = (
        "donante",
        "matricula",
    )
    ordering = (
        "-fecha_inicio",
        "-id_padrinazgo",
    )
    date_hierarchy = "fecha_inicio"
    inlines = (DonacionInline,)


@admin.register(Donacion)
class DonacionAdmin(NoEliminarAdminMixin):
    list_display = (
        "id_donacion",
        "donante",
        "padrinazgo",
        "monto",
        "fecha_compromiso",
        "fecha_ingreso",
        "estado",
        "usuario_confirma",
    )
    list_filter = (
        "estado",
        "fecha_compromiso",
        "fecha_ingreso",
        "metodo_pago",
    )
    search_fields = (
        "donante__nombre_completo",
        "referencia",
        "observaciones",
        "padrinazgo__matricula__numero_matricula",
        "padrinazgo__matricula__estudiante__codigo_estudiante",
    )
    raw_id_fields = (
        "donante",
        "padrinazgo",
        "obligacion",
        "ingreso",
        "usuario_registra",
        "usuario_confirma",
    )
    ordering = (
        "-fecha_compromiso",
        "-id_donacion",
    )
    date_hierarchy = "fecha_compromiso"
