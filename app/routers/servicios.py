"""
Router de servicios: CRUD completo con paginación y filtro por categoría.
- POST /servicios/       → handyman con identidad verificada crea un servicio
- GET  /servicios/       → cualquier usuario autenticado lista servicios (filtro + paginación)
- GET  /servicios/{id}   → cualquier usuario autenticado obtiene un servicio por ID
- PUT  /servicios/{id}   → solo el handyman dueño o admin puede actualizar
- DELETE /servicios/{id} → solo el handyman dueño o admin puede eliminar
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import requiere_rol, usuario_actual
from app.firebase import db
from app.schemas.servicio import ServicioIn, ServicioOut

router = APIRouter(prefix="/servicios", tags=["Servicios"])


def _doc_a_servicio(doc) -> ServicioOut:
    """Convierte un DocumentSnapshot de Firestore en ServicioOut."""
    datos = doc.to_dict()
    return ServicioOut(id=doc.id, **datos)


def _verificar_propietario_o_admin(servicio_data: dict, user: dict) -> None:
    """
    Lanza 403 si el usuario no es el dueño del servicio ni tiene rol admin.
    """
    es_dueno = servicio_data.get("handymanId") == user["uid"]
    es_admin = user.get("rol") == "admin"
    if not es_dueno and not es_admin:
        raise HTTPException(403, "Solo el handyman dueño o un admin puede realizar esta acción")


# ── Crear servicio ────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
def crear(
    data: ServicioIn,
    user=Depends(requiere_rol("handyman")),
):
    """Crea un nuevo servicio. Solo handyman con identidad verificada."""
    if not user.get("identidadVerificada"):
        raise HTTPException(403, "Debes verificar tu identidad antes de publicar servicios")

    _, ref = db.collection("servicios").add({
        **data.model_dump(),
        "handymanId": user["uid"],
        "activo": True,
    })
    return {"id": ref.id}


# ── Listar servicios ──────────────────────────────────────────────────────────

@router.get("/", response_model=list[ServicioOut])
def listar(
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    limit: int = Query(20, ge=1, le=100, description="Máximo de resultados por página"),
    cursor: Optional[str] = Query(None, description="ID del último servicio visto (paginación)"),
    user=Depends(usuario_actual),
):
    """
    Lista servicios con filtro opcional por categoría y paginación basada en cursor.
    El cursor es el ID del último servicio de la página anterior.
    """
    query = db.collection("servicios").order_by("__name__")

    # Filtro por categoría
    if categoria:
        query = query.where("categoria", "==", categoria)

    # Paginación: empezar después del cursor dado
    if cursor:
        cursor_doc = db.collection("servicios").document(cursor).get()
        if cursor_doc.exists:
            query = query.start_after(cursor_doc)

    query = query.limit(limit)
    return [ServicioOut(id=doc.id, **doc.to_dict()) for doc in query.stream()]


# ── Obtener servicio por ID ───────────────────────────────────────────────────

@router.get("/{servicio_id}", response_model=ServicioOut)
def obtener(
    servicio_id: str,
    user=Depends(usuario_actual),
):
    """Obtiene un servicio por su ID. Cualquier usuario autenticado puede consultarlo."""
    doc = db.collection("servicios").document(servicio_id).get()
    if not doc.exists:
        raise HTTPException(404, "Servicio no encontrado")
    return ServicioOut(id=doc.id, **doc.to_dict())


# ── Actualizar servicio ───────────────────────────────────────────────────────

@router.put("/{servicio_id}", response_model=ServicioOut)
def actualizar(
    servicio_id: str,
    data: ServicioIn,
    user=Depends(usuario_actual),
):
    """
    Actualiza un servicio existente.
    Solo el handyman dueño (handymanId == uid) o un admin pueden hacerlo.
    """
    ref = db.collection("servicios").document(servicio_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(404, "Servicio no encontrado")

    _verificar_propietario_o_admin(doc.to_dict(), user)

    ref.update(data.model_dump())
    doc_actualizado = ref.get()
    return ServicioOut(id=doc_actualizado.id, **doc_actualizado.to_dict())


# ── Eliminar servicio ─────────────────────────────────────────────────────────

@router.delete("/{servicio_id}", status_code=204)
def eliminar(
    servicio_id: str,
    user=Depends(usuario_actual),
):
    """
    Elimina un servicio.
    Solo el handyman dueño (handymanId == uid) o un admin pueden hacerlo.
    """
    ref = db.collection("servicios").document(servicio_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(404, "Servicio no encontrado")

    _verificar_propietario_o_admin(doc.to_dict(), user)

    ref.delete()
    # HTTP 204 no devuelve body