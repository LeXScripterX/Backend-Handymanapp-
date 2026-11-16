from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.dependencies import requiere_rol
from app.firebase import db

router = APIRouter(prefix="/admin", tags=["Admin"])


class Valor(BaseModel):
    valor: bool


def _es_reciente(u: dict, limite: datetime) -> bool:
    c = u.get("creado")
    return isinstance(c, datetime) and c >= limite


@router.get("/estadisticas")
def estadisticas(admin=Depends(requiere_rol("admin"))):
    usuarios = {d.id: d.to_dict() for d in db.collection("users").stream()}
    servicios = [d.to_dict() for d in db.collection("servicios").stream()]

    hace_7d = datetime.now(timezone.utc) - timedelta(days=7)

    handymen = {uid: u for uid, u in usuarios.items() if u.get("rol") == "handyman"}
    clientes = [u for u in usuarios.values() if u.get("rol") == "cliente"]

    # Usuarios
    resumen = {
        "total_usuarios": len(usuarios),
        "trabajadores": len(handymen),
        "clientes": len(clientes),
        "registrados_ultimos_7_dias": sum(
            1 for u in usuarios.values() if _es_reciente(u, hace_7d)
        ),
        "activos": sum(1 for u in usuarios.values() if u.get("activo", True)),
        "inactivos": sum(1 for u in usuarios.values() if not u.get("activo", True)),
        "trabajadores_verificados": sum(1 for u in handymen.values() if u.get("identidadVerificada")),
        "trabajadores_sin_verificar": sum(1 for u in handymen.values() if not u.get("identidadVerificada")),
    }

    # Por categoría u oficio
    cats = defaultdict(lambda: {"servicios": 0, "trabajadores": set()})
    for s in servicios:
        c = (s.get("categoria") or "Sin categoría").strip().title()
        cats[c]["servicios"] += 1
        if s.get("handymanId"):
            cats[c]["trabajadores"].add(s["handymanId"])

    por_categoria = []
    for nombre, v in cats.items():
        ids = v["trabajadores"]
        verif = sum(1 for i in ids if usuarios.get(i, {}).get("identidadVerificada"))
        activos = sum(1 for i in ids if usuarios.get(i, {}).get("activo", True))
        por_categoria.append({
            "categoria": nombre,
            "servicios": v["servicios"],
            "trabajadores": len(ids),
            "verificados": verif,
            "sin_verificar": len(ids) - verif,
            "activos": activos,
        })
    por_categoria.sort(key=lambda x: x["trabajadores"], reverse=True)

    return {"resumen": resumen, "por_categoria": por_categoria}


@router.get("/usuarios")
def listar_usuarios(admin=Depends(requiere_rol("admin"))):
    lista = []
    for d in db.collection("users").stream():
        u = d.to_dict()
        lista.append({
            "id": d.id,
            "nombre": u.get("nombre", ""),
            "email": u.get("email", ""),
            "rol": u.get("rol", ""),
            "verificado": bool(u.get("identidadVerificada", False)),
            "activo": u.get("activo", True),
        })
    return lista


def _actualizar_usuario(uid: str, campos: dict):
    ref = db.collection("users").document(uid)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    ref.update(campos)


@router.patch("/usuarios/{uid}/verificado")
def set_verificado(uid: str, body: Valor, admin=Depends(requiere_rol("admin"))):
    _actualizar_usuario(uid, {"identidadVerificada": body.valor})
    return {"id": uid, "verificado": body.valor}


@router.patch("/usuarios/{uid}/activo")
def set_activo(uid: str, body: Valor, admin=Depends(requiere_rol("admin"))):
    _actualizar_usuario(uid, {"activo": body.valor})
    return {"id": uid, "activo": body.valor}