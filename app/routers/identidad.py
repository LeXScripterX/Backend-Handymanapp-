"""
Router de identidad facial:
  POST /identidad/registrar-rostro  → Registra embedding facial + verifica identidad
  POST /identidad/validar-rostro    → Compara selfie nueva con embedding guardado
  DELETE /identidad/rostro          → Borra datos biométricos (derecho de supresión)

  Notas de seguridad:
  - Nunca se guardan imágenes en disco de forma permanente
  - Los archivos temporales siempre se limpian en bloques try/finally
  - Rate limiting simple por usuario guardado en Firestore
  - Se exige consentimiento explícito para registrar
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from firebase_admin import firestore as fs

from app.config import settings
from app.dependencies import requiere_rol, usuario_actual
from app.firebase import db
from app.services.facial import (
    _validar_archivo,
    calcular_embedding,
    comparar_rostros,
    comparar_rostros_bytes,
    distancia_coseno,
)

router = APIRouter(prefix="/identidad", tags=["Identidad"])
logger = logging.getLogger("handyman.identidad")


# ── Helpers de rate limiting ──────────────────────────────────────────────────

def _verificar_rate_limit(uid: str) -> None:
    """
    Verifica que el usuario no supere el límite de intentos faciales por hora.
    Guarda el contador en users/{uid}.intentosFaciales (dict con 'contador' y 'hora').
    Lanza HTTPException 429 si se supera el límite.
    """
    ref = db.collection("users").document(uid)
    doc = ref.get()
    datos = doc.to_dict() or {}

    hora_actual = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    intentos_info = datos.get("intentosFaciales", {})

    # Extraer hora guardada (puede ser datetime o string ISO)
    hora_guardada = intentos_info.get("hora")
    if isinstance(hora_guardada, str):
        try:
            hora_guardada = datetime.fromisoformat(hora_guardada)
        except ValueError:
            hora_guardada = None

    # Resetear si cambió la hora
    if hora_guardada is None or hora_guardada.replace(tzinfo=timezone.utc) < hora_actual:
        contador = 0
    else:
        contador = intentos_info.get("contador", 0)

    if contador >= settings.intentos_max_por_hora:
        raise HTTPException(
            429,
            f"Límite de {settings.intentos_max_por_hora} intentos por hora alcanzado. "
            "Intenta de nuevo más tarde.",
        )

    # Incrementar contador
    ref.update({
        "intentosFaciales": {
            "contador": contador + 1,
            "hora": hora_actual.isoformat(),
        }
    })


# ── Registrar rostro ──────────────────────────────────────────────────────────

@router.post("/registrar-rostro")
def registrar_rostro(
    selfie: UploadFile = File(..., description="Foto del rostro del usuario"),
    documento: UploadFile = File(..., description="Foto del documento de identidad"),
    consentimiento: bool = Form(..., description="El usuario acepta el procesamiento biométrico"),
    user=Depends(requiere_rol("handyman")),
):
    """
    Registra la identidad biométrica del handyman:
    1. Valida consentimiento explícito
    2. Aplica rate limiting
    3. Verifica que selfie y documento tengan el mismo rostro (DeepFace.verify)
    4. Calcula embedding de la selfie (DeepFace.represent)
    5. Guarda embedding en users/{uid}/biometria/facial (NO la imagen)
    6. Marca identidadVerificada=true en users/{uid}
    """
    if not consentimiento:
        raise HTTPException(
            400,
            "Se requiere consentimiento explícito para procesar datos biométricos. "
            "Envía consentimiento=true para continuar.",
        )

    _verificar_rate_limit(user["uid"])

    # Leer bytes (valida tipo y tamaño)
    bytes_selfie = _validar_archivo(selfie)
    bytes_doc = _validar_archivo(documento)

    try:
        # Paso 1: verificar que selfie y documento muestran el mismo rostro.
        resultado_verificacion = comparar_rostros_bytes(
            bytes_selfie, selfie.content_type, bytes_doc, documento.content_type
        )

        if not resultado_verificacion.get("verificado"):
            raise HTTPException(
                422,
                "Las imágenes no corresponden al mismo rostro. "
                f"Distancia: {resultado_verificacion.get('distancia', '?'):.4f}",
            )

        # Paso 2: calcular embedding de la selfie (bytes, sin archivo temporal nuevo)
        embedding = calcular_embedding(bytes_selfie, selfie.content_type)

    except HTTPException:
        raise  # re-lanzar errores HTTP controlados
    except Exception as exc:
        logger.error("Error al procesar biometría: %s", type(exc).__name__)
        raise HTTPException(500, "Error al procesar las imágenes") from exc


    # Guardar embedding en subcolección biometria/facial (NUNCA la imagen)
    uid = user["uid"]
    db.collection("users").document(uid) \
      .collection("biometria").document("facial") \
      .set({
          "embedding": embedding,
          "modelo": "Facenet",
          "creado": fs.SERVER_TIMESTAMP,
          "consentimiento": True,
      })

    # Marcar identidad como verificada
    db.collection("users").document(uid).update({"identidadVerificada": True})

    logger.info("Rostro registrado exitosamente [modelo=Facenet]")
    return {"ok": True, "mensaje": "Identidad verificada y rostro registrado correctamente"}


# ── Validar rostro ────────────────────────────────────────────────────────────

@router.post("/validar-rostro")
def validar_rostro(
    selfie: UploadFile = File(..., description="Foto nueva del rostro a validar"),
    user=Depends(requiere_rol("handyman")),
):
    """
    Valida una selfie nueva comparándola con el embedding guardado.
    Útil para reconfirmar identidad antes de acciones sensibles.
    Devuelve {coincide: bool, distancia: float}.
    """
    _verificar_rate_limit(user["uid"])

    # Obtener embedding guardado
    doc_biometria = (
        db.collection("users").document(user["uid"])
          .collection("biometria").document("facial")
          .get()
    )
    if not doc_biometria.exists:
        raise HTTPException(
            404,
            "No hay un rostro registrado para este usuario. "
            "Usa POST /identidad/registrar-rostro primero.",
        )

    embedding_guardado = doc_biometria.to_dict().get("embedding", [])
    if not embedding_guardado:
        raise HTTPException(500, "El embedding guardado está vacío o corrupto")

    # Calcular embedding de la selfie nueva
    bytes_selfie = _validar_archivo(selfie)
    try:
        embedding_nuevo = calcular_embedding(bytes_selfie, selfie.content_type)
    except HTTPException:
        raise

    # Comparar por distancia coseno
    distancia = distancia_coseno(embedding_guardado, embedding_nuevo)
    coincide = distancia <= settings.umbral_facial

    logger.info("Validación facial: coincide=%s distancia=%.4f umbral=%.2f",
                coincide, distancia, settings.umbral_facial)

    return {"coincide": coincide, "distancia": round(distancia, 4)}


# ── Borrar datos biométricos ──────────────────────────────────────────────────

@router.delete("/rostro", status_code=200)
def borrar_rostro(user=Depends(usuario_actual)):
    """
    Borra los datos biométricos del usuario (derecho de supresión GDPR/LGPD).
    Elimina la subcolección biometria/ y marca identidadVerificada=false.
    """
    uid = user["uid"]
    biometria_ref = (
        db.collection("users").document(uid).collection("biometria")
    )

    # Borrar todos los documentos de la subcolección
    docs = biometria_ref.stream()
    borrados = 0
    for doc in docs:
        doc.reference.delete()
        borrados += 1

    # Resetear estado de verificación
    db.collection("users").document(uid).update({"identidadVerificada": False})

    logger.info("Datos biométricos eliminados [documentos=%d]", borrados)
    return {
        "ok": True,
        "mensaje": "Datos biométricos eliminados. identidadVerificada se ha reseteado a false.",
    }


# ── Endpoint original (retrocompatibilidad) ───────────────────────────────────

@router.post("/verificar", deprecated=True)
def verificar(
    selfie: UploadFile = File(...),
    documento: UploadFile = File(...),
    user=Depends(requiere_rol("handyman")),
):
    """
    [DEPRECADO] Usa /identidad/registrar-rostro en su lugar.
    Compara selfie con documento y actualiza identidadVerificada pero NO guarda embedding.
    """
    try:
        res = comparar_rostros(selfie, documento)
    except HTTPException:
        raise

    db.collection("users").document(user["uid"]).update(
        {"identidadVerificada": res["verificado"]}
    )
    return res