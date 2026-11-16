"""
Servicio de reconocimiento facial usando DeepFace con import perezoso.
No escribe imágenes permanentes en disco; todo se limpia en finally.
"""
import io
import os
import math
import tempfile
import logging
from typing import Optional

from fastapi import UploadFile, HTTPException

from app.config import settings

logger = logging.getLogger("handyman.facial")

# Tipos MIME permitidos y sus extensiones de archivo temporal
_TIPOS_PERMITIDOS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


# ── Utilidades internas ───────────────────────────────────────────────────────

def _validar_archivo(upload: UploadFile, max_bytes: Optional[int] = None) -> bytes:
    """
    Valida tipo MIME y tamaño del archivo subido.
    Devuelve los bytes leídos para reutilizar sin leer el stream dos veces.
    Lanza HTTPException 400/413 si no pasa la validación.
    """
    if max_bytes is None:
        max_bytes = settings.max_imagen_bytes

    # Validar tipo de contenido
    content_type = upload.content_type or ""
    if content_type not in _TIPOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de imagen no permitido: '{content_type}'. Solo se acepta jpeg o png.",
        )

    # Leer y validar tamaño
    datos = upload.file.read()
    if len(datos) > max_bytes:
        mb = max_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"La imagen supera el tamaño máximo permitido de {mb:.0f} MB.",
        )

    return datos


def _guardar_temp(datos: bytes, content_type: str) -> str:
    """Escribe bytes en un archivo temporal y devuelve la ruta."""
    extension = _TIPOS_PERMITIDOS.get(content_type, ".jpg")
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as f:
        f.write(datos)
        return f.name


def comparar_rostros_bytes(
    datos_selfie: bytes, tipo_selfie: str, datos_doc: bytes, tipo_doc: str
) -> dict:
    """
    Compara dos rostros a partir de sus bytes con DeepFace.verify.
    Guarda temporales y los limpia en el bloque finally.
    """
    from deepface import DeepFace  # import perezoso

    ruta_a = _guardar_temp(datos_selfie, tipo_selfie)
    ruta_b = _guardar_temp(datos_doc, tipo_doc)
    try:
        r = DeepFace.verify(ruta_a, ruta_b, model_name="Facenet", enforce_detection=True)
        return {"verificado": bool(r["verified"]), "distancia": r["distance"]}
    except ValueError as exc:
        raise HTTPException(400, "No se detectó un rostro en alguna imagen") from exc
    finally:
        _limpiar(ruta_a, ruta_b)


def comparar_rostros(selfie: UploadFile, documento: UploadFile) -> dict:
    """
    Compara dos imágenes con DeepFace.verify recibiendo UploadFile.
    Mantiene compatibilidad con el endpoint original.
    """
    datos_selfie = _validar_archivo(selfie)
    datos_doc = _validar_archivo(documento)
    return comparar_rostros_bytes(
        datos_selfie, selfie.content_type, datos_doc, documento.content_type
    )


def calcular_embedding(datos: bytes, content_type: str) -> list:
    """
    Calcula el embedding facial de una imagen con DeepFace (modelo Facenet).
    Devuelve una lista de floats (vector 128-dimensional).
    Lanza HTTPException 400 si no se detecta un rostro.
    """
    from deepface import DeepFace  # import perezoso

    ruta = _guardar_temp(datos, content_type)
    try:
        resultado = DeepFace.represent(
            ruta,
            model_name="Facenet",
            enforce_detection=True,
        )
        # represent devuelve una lista de dicts; tomamos el primer rostro detectado
        if not resultado:
            raise HTTPException(400, "No se detectó ningún rostro en la imagen")
        return resultado[0]["embedding"]
    except ValueError as exc:
        raise HTTPException(400, "No se detectó un rostro válido en la imagen") from exc
    finally:
        _limpiar(ruta)


def distancia_coseno(vec_a: list, vec_b: list) -> float:
    """
    Calcula la distancia coseno entre dos vectores de embedding.
    Retorna 0.0 si son idénticos, 1.0 si son completamente diferentes.
    """
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a ** 2 for a in vec_a))
    mag_b = math.sqrt(sum(b ** 2 for b in vec_b))
    if mag_a == 0 or mag_b == 0:
        return 1.0
    similitud = dot / (mag_a * mag_b)
    # Distancia = 1 - similitud (en rango [0, 1])
    return round(1.0 - similitud, 6)


def _limpiar(*rutas: str) -> None:
    """Elimina archivos temporales ignorando errores si ya no existen."""
    for ruta in rutas:
        try:
            os.remove(ruta)
        except OSError:
            pass  # Ya fue eliminado o nunca existió