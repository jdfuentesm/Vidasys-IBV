from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe
from django.views.decorators.cache import never_cache


@never_cache
@require_safe
def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('calendario_financiero') IS NOT NULL, to_regprocedure('estudiante_esta_solvente(bigint,date)') IS NOT NULL, to_regprocedure('recalcular_estado_obligacion(bigint)') IS NOT NULL")
            if not all(cursor.fetchone()):
                return JsonResponse({'status': 'unavailable'}, status=503)
        return JsonResponse({'status': 'ok'})
    except DatabaseError:
        return JsonResponse({'status': 'unavailable'}, status=503)
