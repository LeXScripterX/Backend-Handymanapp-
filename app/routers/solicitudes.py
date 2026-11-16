"""
Router de solicitudes de servicio.
Flujo de estados UI: pendiente (nuevas) → en_camino → en_curso → completada / rechazada
(admite 'aceptada' para retrocompatibilidad)

Permisos:
  - POST  /solicitudes/           → cliente (crea)
  - GET   /solicitudes/           → cada rol ve solo las suyas
  - GET   /solicitudes/{id}       → dueño (cliente o handyman) o admin
  - PATCH /solicitudes/{id}/estado → handyman avanza el estado; cliente/admin pueden confirmar
"""
from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import firestore as fs

from app.dependencies import requiere_rol, usuario_actual
from app.firebase import db
from app.schemas.solicitud import SolicitudIn, SolicitudOut, CambioEstadoIn

router = APIRouter(prefix="/solicitudes", tags=["Solicitudes"])

# Transiciones de estado permitidas por rol
_TRANSICIONES = {
    "pendiente": {
        "handyman": ["aceptada", "en_camino", "en_curso", "rechazada"],
        "cliente": [],
        "admin": ["aceptada", "en_camino", "en_curso", "rechazada", "completada"],
    },
    "aceptada": {
        "handyman": ["en_camino", "en_curso", "completada"],
        "cliente": ["completada"],
        "admin": ["en_camino", "en_curso", "completada", "rechazada"],
    },
    "en_camino": {
        "handyman": ["en_curso", "completada"],
        "cliente": ["completada"],
        "admin": ["en_curso", "completada", "rechazada"],
    },
    "en_curso": {
        "handyman": ["completada"],
        "cliente": ["completada"],
        "admin": ["completada"],
    },
    "rechazada": {
        "handyman": [],
        "cliente": [],
        "admin": [],
    },
    "completada": {
        "handyman": [],
        "cliente": [],
        "admin": [],
    },
}


def _doc_a_solicitud(doc) -> SolicitudOut:
    """Convierte un DocumentSnapshot en SolicitudOut."""
    datos = doc.to_dict()
    if datos.get("creado"):
        try:
            datos["creado"] = datos["creado"].isoformat()
        except Exception:
            datos["creado"] = str(datos["creado"])
    return SolicitudOut(id=doc.id, **datos)


# ── Crear solicitud ───────────────────────────────────────────────────────────

@router.post("/", status_code=201)
def crear_solicitud(
    data: SolicitudIn,
    user=Depends(requiere_rol("cliente")),
):
    """El cliente crea una solicitud a un servicio existente con dirección y precio opcional."""
    servicio_doc = db.collection("servicios").document(data.servicioId).get()
    if not servicio_doc.exists:
        raise HTTPException(404, "El servicio solicitado no existe")

    servicio = servicio_doc.to_dict()
    handyman_id = servicio.get("handymanId")

    if handyman_id == user["uid"]:
        raise HTTPException(400, "No puedes crear una solicitud a tu propio servicio")

    # Si no especificó precio especial, tomamos la tarifa base del servicio
    precio_final = data.precio if data.precio is not None else servicio.get("precio", 0.0)

    _, ref = db.collection("solicitudes").add({
        "servicioId": data.servicioId,
        "servicioTitulo": servicio.get("titulo", "Servicio"),
        "clienteId": user["uid"],
        "clienteNombre": user.get("nombre", "Cliente"),
        "handymanId": handyman_id,
        "mensaje": data.mensaje,
        "direccion": data.direccion,
        "ubicacionDetalle": data.ubicacionDetalle,
        "precio": precio_final,
        "estado": "pendiente",
        "creado": fs.SERVER_TIMESTAMP,
    })
    return {"id": ref.id}


# ── Listar solicitudes ────────────────────────────────────────────────────────

@router.get("/", response_model=list[SolicitudOut])
def listar_solicitudes(user=Depends(usuario_actual)):
    """
    Lista solicitudes filtradas por rol:
    - cliente  → sus propias solicitudes
    - handyman → solicitudes dirigidas a él
    - admin    → todas las solicitudes
    """
    col = db.collection("solicitudes")
    rol = user.get("rol")

    if rol == "cliente":
        docs = col.where("clienteId", "==", user["uid"]).stream()
    elif rol == "handyman":
        docs = col.where("handymanId", "==", user["uid"]).stream()
    else:
        docs = col.stream()

    return [_doc_a_solicitud(doc) for doc in docs]


# ── Obtener solicitud por ID ──────────────────────────────────────────────────

@router.get("/{solicitud_id}", response_model=SolicitudOut)
def obtener_solicitud(
    solicitud_id: str,
    user=Depends(usuario_actual),
):
    """Obtiene una solicitud por ID. Solo participante o admin."""
    doc = db.collection("solicitudes").document(solicitud_id).get()
    if not doc.exists:
        raise HTTPException(404, "Solicitud no encontrada")

    datos = doc.to_dict()
    uid = user["uid"]
    rol = user.get("rol")

    es_participante = datos.get("clienteId") == uid or datos.get("handymanId") == uid
    if not es_participante and rol != "admin":
        raise HTTPException(403, "No tienes acceso a esta solicitud")

    return _doc_a_solicitud(doc)


# ── Cambiar estado de solicitud ───────────────────────────────────────────────

@router.patch("/{solicitud_id}/estado")
def cambiar_estado(
    solicitud_id: str,
    data: CambioEstadoIn,
    user=Depends(usuario_actual),
):
    """
    Avanza el estado del trabajo según las transiciones del flujo:
    pendiente -> aceptada / en_camino / en_curso / rechazada
    en_camino -> en_curso -> completada
    """
    ref = db.collection("solicitudes").document(solicitud_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(404, "Solicitud no encontrada")

    datos = doc.to_dict()
    uid = user["uid"]
    rol = user.get("rol")
    estado_actual = datos.get("estado", "pendiente")
    nuevo_estado = data.estado

    es_participante = datos.get("clienteId") == uid or datos.get("handymanId") == uid
    if not es_participante and rol != "admin":
        raise HTTPException(403, "No tienes acceso a esta solicitud")

    transiciones_permitidas = _TRANSICIONES.get(estado_actual, {}).get(rol, [])
    if nuevo_estado not in transiciones_permitidas:
        raise HTTPException(
            422,
            f"El rol '{rol}' no puede cambiar el estado de '{estado_actual}' a '{nuevo_estado}'",
        )

    ref.update({"estado": nuevo_estado})
    return {"ok": True, "estado": nuevo_estado}
