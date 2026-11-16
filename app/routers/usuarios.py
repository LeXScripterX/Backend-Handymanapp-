"""
Router de usuarios: registro de perfil, consulta y actualización de perfil en Firestore.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import auth, firestore

from app.config import settings
from app.dependencies import token_valido, usuario_actual
from app.firebase import db
from app.schemas.usuario import (
    CuentaIn,
    CuentaOut,
    RegistroIn,
    RegistroOut,
    PerfilOut,
    PerfilUpdateIn,
)

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


def _guardar_perfil(
    uid: str,
    *,
    nombre: str,
    email: str,
    telefono: str | None,
    rol: str,
    terminos_aceptados: bool,
    foto_url: str | None = None,
) -> None:
    db.collection("users").document(uid).set({
        "nombre": nombre,
        "email": email,
        "telefono": telefono,
        "rol": rol,
        "identidadVerificada": False,
        "disponible": True,
        "calificacion": 5.0,
        "trabajosCompletados": 0,
        "experienciaAnos": 0.0,
        "gananciasHoy": 0.0,
        "completadosHoy": 0,
        "fotoUrl": foto_url,
        "terminosAceptados": terminos_aceptados,
        "creado": firestore.SERVER_TIMESTAMP,
    })


def _id_token_con_password(email: str, password: str) -> str | None:
    """Inicia sesión en Identity Toolkit para devolver un idToken usable en Swagger."""
    if not settings.firebase_web_api_key:
        return None
    try:
        respuesta = httpx.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
            params={"key": settings.firebase_web_api_key},
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=15,
        )
        datos = respuesta.json()
        return datos.get("idToken")
    except Exception:
        return None


@router.post(
    "/cuenta",
    status_code=201,
    response_model=CuentaOut,
    summary="Crear cuenta nueva (Auth + perfil)",
)
def crear_cuenta(data: CuentaIn):
    """
    Crea el usuario en Firebase Authentication y el perfil en Firestore.
    No requiere token. Pensado para pruebas en Swagger.

    Copia el `idToken` de la respuesta y pégalo en Authorize para los demás endpoints.
    """
    try:
        cuenta = auth.create_user(email=data.email, password=data.password)
    except auth.EmailAlreadyExistsError:
        raise HTTPException(409, "Ese correo ya está registrado en Firebase Auth")
    except Exception as exc:
        raise HTTPException(400, f"No se pudo crear la cuenta: {exc}") from exc

    _guardar_perfil(
        cuenta.uid,
        nombre=data.nombre,
        email=data.email,
        telefono=data.telefono,
        rol=data.rol,
        terminos_aceptados=data.terminosAceptados,
    )

    id_token = _id_token_con_password(data.email, data.password)
    aviso = None
    if not id_token:
        aviso = (
            "Cuenta creada, pero no hay idToken. Configura FIREBASE_WEB_API_KEY en .env "
            "o ejecuta: python get_token.py "
            f"{data.email} <password>"
        )

    return CuentaOut(
        ok=True,
        uid=cuenta.uid,
        email=data.email,
        rol=data.rol,
        idToken=id_token,
        aviso=aviso,
    )


@router.post("/registro", status_code=201, response_model=RegistroOut)
def registro(data: RegistroIn, decoded=Depends(token_valido)):
    """
    Crea el perfil del usuario en Firestore después de autenticarse en Firebase Auth.
    El rol 'admin' no puede autoasignarse.
    """
    ref = db.collection("users").document(decoded["uid"])
    if ref.get().exists:
        raise HTTPException(409, "El perfil ya existe")

    _guardar_perfil(
        decoded["uid"],
        nombre=data.nombre,
        email=decoded.get("email", ""),
        telefono=data.telefono,
        rol=data.rol,
        terminos_aceptados=data.terminosAceptados,
        foto_url=data.fotoUrl or decoded.get("picture"),
    )
    return RegistroOut(ok=True, uid=decoded["uid"], rol=data.rol)


@router.get("/perfil", response_model=PerfilOut)
def ver_perfil(user=Depends(usuario_actual)):
    """
    Devuelve los datos completos del perfil del usuario autenticado (datos, métricas, disponibilidad).
    Alimenta la pantalla de Perfil y el Inicio del Handyman.
    """
    # Si creado es timestamp, lo convertimos a string seguro
    creado = user.get("creado")
    creado_str = creado.isoformat() if hasattr(creado, "isoformat") else str(creado) if creado else None

    return PerfilOut(
        uid=user["uid"],
        nombre=user.get("nombre", ""),
        email=user.get("email", ""),
        telefono=user.get("telefono"),
        rol=user.get("rol", "cliente"),
        identidadVerificada=bool(user.get("identidadVerificada", False)),
        disponible=bool(user.get("disponible", True)),
        calificacion=float(user.get("calificacion", 5.0)),
        trabajosCompletados=int(user.get("trabajosCompletados", 0)),
        experienciaAnos=float(user.get("experienciaAnos", 0.0)),
        gananciasHoy=float(user.get("gananciasHoy", 0.0)),
        completadosHoy=int(user.get("completadosHoy", 0)),
        fotoUrl=user.get("fotoUrl"),
        creado=creado_str,
    )


@router.put("/perfil", response_model=PerfilOut)
def actualizar_perfil(data: PerfilUpdateIn, user=Depends(usuario_actual)):
    """
    Permite al usuario editar su información personal (nombre, teléfono, avatar, experiencia)
    y al handyman alternar el switch 'Disponible para trabajos'.
    """
    ref = db.collection("users").document(user["uid"])
    campos_a_actualizar = data.model_dump(exclude_unset=True)

    if campos_a_actualizar:
        ref.update(campos_a_actualizar)

    # Obtener el documento actualizado
    doc_actualizado = ref.get().to_dict() or {}
    return ver_perfil(user={"uid": user["uid"], **doc_actualizado})