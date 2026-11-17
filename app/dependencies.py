# app/dependencies.py

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.firebase import db

# ── Configuración del esquema de seguridad ────────────────────────────────────
bearer = HTTPBearer(
    scheme_name="Bearer JWT",
    bearerFormat="JWT",
    description=(
        "idToken de Firebase Auth. Pégalo aquí **sin** el prefijo `Bearer `. "
        "Casi todos los endpoints lo requieren; no es un campo del body."
    ),
)

# ── 1. Validación del Token ───────────────────────────────────────────────────

def token_valido(cred: HTTPAuthorizationCredentials = Security(bearer)):
    """
    Verifica la validez del token de Firebase.
    Se utiliza la librería de Google con un margen de tolerancia (clock_skew)
    para evitar errores de desfase de reloj entre el cliente y el servidor.
    """
    try:
        decoded_token = id_token.verify_firebase_token(
            cred.credentials,
            google_requests.Request(),
            audience="handyman-a3204",  # ID del proyecto de Firebase
            clock_skew_in_seconds=60    # Tolerancia de 60 segundos
        )
        return decoded_token
    except Exception as e:
        print("ERROR TOKEN:", repr(e))
        raise HTTPException(401, f"Token inválido: {e}")

# ── 2. Dependencias de Usuario ────────────────────────────────────────────────

def usuario_actual(decoded=Depends(token_valido)):
    """
    Dependencia estricta: Requiere que el usuario exista en Firestore.
    Útil para endpoints que necesitan leer o modificar el perfil.
    """
    # Google devuelve 'user_id' o 'sub' en el token, no 'uid'
    uid = decoded.get("user_id") or decoded.get("sub") or decoded.get("uid")
    
    if not uid:
        raise HTTPException(401, "Token no contiene un ID de usuario válido")

    doc = db.collection("users").document(uid).get()
    
    if not doc.exists:
        raise HTTPException(403, "Usuario sin perfil, regístrate primero")
        
    # Devolvemos 'uid' explícitamente para mantener compatibilidad con los routers
    return {"uid": uid, **doc.to_dict()}


def usuario_autenticado(decoded=Depends(token_valido)):
    """
    Dependencia flexible: Solo verifica que el token sea válido.
    Útil para el endpoint de CREAR perfil (el usuario aún no existe en Firestore).
    """
    uid = decoded.get("user_id") or decoded.get("sub") or decoded.get("uid")
    
    return {
        "uid": uid,
        "email": decoded.get("email"),
        "nombre": decoded.get("name", "Usuario"),
    }

# ── 3. Verificación de Roles ──────────────────────────────────────────────────

def requiere_rol(*roles: str):
    """
    Fábrica de dependencias para restringir el acceso según el rol del usuario.
    Ejemplo de uso: Depends(requiere_rol("admin", "handyman"))
    """
    def checker(user=Depends(usuario_actual)):
        if user.get("rol") not in roles:
            raise HTTPException(403, "No tienes permiso")
        return user
    return checker