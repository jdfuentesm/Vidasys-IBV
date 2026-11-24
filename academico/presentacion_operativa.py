"""Vista previa de configuración existente; no valida ni ejecuta matrículas."""
from django.core.exceptions import ValidationError
from financiero.calendario import leer
from .models import Curso


def ciclos_para_matricula(form):
    ciclos = list(form.fields['ciclo'].queryset)
    por_ciclo = {c.pk: [] for c in ciclos}
    for curso in Curso.objects.filter(ciclo_id__in=por_ciclo).select_related('materia').order_by('materia__nombre', 'pk'):
        por_ciclo[curso.ciclo_id].append(curso)
    resultado = []
    for ciclo in ciclos:
        try:
            calendario = leer(ciclo)
            aviso = ''
        except ValidationError as error:
            calendario = None
            aviso = ' '.join(error.messages)
        resultado.append({'ciclo': ciclo, 'cursos': por_ciclo[ciclo.pk], 'calendario': calendario, 'aviso': aviso})
    return resultado
