from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth
from app.firebase import db

bearer = HTTPBearer(
    scheme_name="Bearer JWT",
    bearerFormat="JWT",
    description=(
        "idToken de Firebase Auth. Pégalo aquí **sin** el prefijo `Bearer `. "
        "Casi todos los endpoints lo requieren; no es un campo del body."
    ),
)

def token_valido(cred: HTTPAuthorizationCredentials = Security(bearer)):
    try:
        return auth.verify_id_token(cred.credentials)
    except Exception as e:
        print("ERROR TOKEN:", repr(e))
        raise HTTPException(401, f"Token inválido: {e}")

def usuario_actual(decoded=Depends(token_valido)):
    doc = db.collection("users").document(decoded["uid"]).get()
    if not doc.exists:
        raise HTTPException(403, "Usuario sin perfil, regístrate primero")
    return {"uid": decoded["uid"], **doc.to_dict()}

def requiere_rol(*roles: str):
    def checker(user=Depends(usuario_actual)):
        if user.get("rol") not in roles:
            raise HTTPException(403, "No tienes permiso")
        return user
    return checker