"""Comprobantes privados en BD: sin MEDIA_URL, nombres originales ni archivos huérfanos."""
import hashlib
import io
import uuid
import warnings
from PIL import Image
from pypdf import PdfReader
from django.core.exceptions import ValidationError
from .models import ComprobantePrivado

MAXIMO = 5 * 1024 * 1024


def validar_archivo(archivo):
    if archivo is None:
        return None
    if archivo.size > MAXIMO:
        raise ValidationError('El comprobante no puede superar 5 MiB.')
    archivo.seek(0)
    contenido = archivo.read(MAXIMO + 1)
    if not contenido or len(contenido) > MAXIMO:
        raise ValidationError('Documento vacío o superior a 5 MiB.')
    try:
        if contenido.startswith(b'%PDF-'):
            pdf = PdfReader(io.BytesIO(contenido), strict=True)
            if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 100:
                raise ValueError('PDF cifrado o demasiadas páginas')
            # No aceptar acciones, JavaScript, formularios, adjuntos ni contenido ejecutable.
            vistos=set()
            def recorrer(obj, profundidad=0):
                if profundidad>50:raise ValueError('PDF demasiado complejo')
                if hasattr(obj,'get_object'):obj=obj.get_object()
                if id(obj) in vistos:return
                vistos.add(id(obj))
                if isinstance(obj,dict):
                    if any(k in obj for k in ('/AA','/OpenAction','/JS','/JavaScript','/Launch','/EmbeddedFiles','/EmbeddedFile','/RichMedia','/AcroForm')):
                        raise ValueError('Contenido activo no admitido')
                    if str(obj.get('/S','')) in ('/JavaScript','/Launch','/GoToR','/SubmitForm','/ImportData'):
                        raise ValueError('Acción externa no admitida')
                    for valor in obj.values():recorrer(valor,profundidad+1)
                elif isinstance(obj,(list,tuple)):
                    for valor in obj:recorrer(valor,profundidad+1)
            recorrer(pdf.trailer)
            mime,extension='application/pdf','pdf'
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(contenido)) as imagen:
                    if imagen.format not in ('PNG','JPEG') or imagen.width*imagen.height>20000000:
                        raise ValueError('Imagen no admitida')
                    extension='png' if imagen.format=='PNG' else 'jpg'
                    imagen.verify()
                with Image.open(io.BytesIO(contenido)) as imagen:imagen.load()
            mime='image/png' if extension=='png' else 'image/jpeg'
    except Exception as exc:
        raise ValidationError('Comprobante inválido. Use PDF sin contenido activo (hasta 100 páginas), PNG o JPEG válido.') from exc
    return {'contenido':contenido,'sha256':hashlib.sha256(contenido).hexdigest(),
            'tamano':len(contenido),'mime':mime,'extension':extension}


def huella(datos):
    return datos['sha256'] if datos else None


def guardar(datos,operador):
    if datos is None:return None
    return ComprobantePrivado.objects.create(nombre=f'{uuid.uuid4().hex}.{datos["extension"]}',
        mime=datos['mime'],contenido=datos['contenido'],sha256=datos['sha256'],tamano=datos['tamano'],operador=operador)
