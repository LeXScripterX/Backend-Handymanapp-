"""
Esquemas Pydantic para usuarios y perfil.
"""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class RegistroIn(BaseModel):
    """Datos de entrada para registrar un nuevo usuario."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nombre": "Ana Pérez",
                "rol": "cliente",
                "telefono": "3001234567",
                "terminosAceptados": True,
            }
        }
    )

    nombre: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Nombre completo del usuario",
    )
    rol: Literal["cliente", "handyman"] = Field(
        ...,
        description="Rol del usuario. El rol 'admin' no puede autoasignarse.",
    )
    telefono: Optional[str] = Field(
        None,
        description="Número de celular / WhatsApp (ej: 300 000 0000)",
    )
    terminosAceptados: bool = Field(
        True,
        description="Aceptación de términos y condiciones de HandymanApp",
    )
    fotoUrl: Optional[str] = Field(
        None,
        description="URL de la foto de perfil o avatar",
    )


class RegistroOut(BaseModel):
    """Respuesta al registrar un usuario exitosamente."""

    ok: bool
    uid: str
    rol: str


class CuentaIn(BaseModel):
    """Alta completa para Swagger: Firebase Auth + perfil en Firestore."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "daniiel@gmail.com",
                "password": "prueba123",
                "nombre": "Ana Pérez",
                "rol": "cliente",
                "telefono": "3001234567",
                "terminosAceptados": True,
            }
        }
    )

    email: str = Field(..., description="Correo de la cuenta en Firebase Auth")
    password: str = Field(..., min_length=6, description="Mínimo 6 caracteres (requisito de Firebase)")
    nombre: str = Field(..., min_length=2, max_length=100)
    rol: Literal["cliente", "handyman"] = Field(...)
    telefono: Optional[str] = None
    terminosAceptados: bool = True


class CuentaOut(BaseModel):
    """Respuesta al crear cuenta completa."""

    ok: bool
    uid: str
    email: str
    rol: str
    idToken: Optional[str] = None
    aviso: Optional[str] = None


class PerfilUpdateIn(BaseModel):
    """Datos para editar información personal o disponibilidad del usuario."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nombre": "Ana Pérez",
                "telefono": "3001234567",
                "disponible": True,
                "experienciaAnos": 1.5,
            }
        }
    )

    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    telefono: Optional[str] = None
    disponible: Optional[bool] = Field(
        None, description="Switch de disponibilidad para recibir trabajos (handyman)"
    )
    fotoUrl: Optional[str] = None
    experienciaAnos: Optional[float] = Field(
        None, ge=0, description="Años de experiencia (ej: 1.5)"
    )


class PerfilOut(BaseModel):
    """Datos completos del perfil para la pantalla de perfil y home."""

    uid: str
    nombre: str
    email: Optional[str] = ""
    telefono: Optional[str] = None
    rol: str
    identidadVerificada: bool = False
    disponible: bool = True
    calificacion: float = 5.0
    trabajosCompletados: int = 0
    experienciaAnos: float = 0.0
    gananciasHoy: float = 0.0
    completadosHoy: int = 0
    fotoUrl: Optional[str] = None
    creado: Optional[str] = None
