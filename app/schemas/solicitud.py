"""
Esquemas Pydantic para solicitudes de servicio.
Adaptado a las pestañas de Operaciones de la app:
[Nuevos] -> [En camino] -> [En curso] -> [Finalizados]
"""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

# Estados de la solicitud: admite los estados de UI y retrocompatibilidad con 'aceptada'
EstadoSolicitud = Literal[
    "pendiente",
    "aceptada",
    "en_camino",
    "en_curso",
    "completada",
    "rechazada",
]


class SolicitudIn(BaseModel):
    """Datos de entrada para crear una nueva solicitud desde la app cliente."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "servicioId": "abc123servicio",
                "mensaje": "Se quemó el breaker de la cocina y no hay luz en esa zona.",
                "direccion": "Cra 15 #85-20",
                "ubicacionDetalle": "Chapinero",
                "precio": 45000,
            }
        }
    )

    servicioId: str = Field(
        ...,
        description="ID del servicio que se solicita",
    )
    mensaje: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Detalle o descripción de la avería / solicitud (10 a 500 caracteres)",
    )
    direccion: Optional[str] = Field(
        None,
        description="Dirección del servicio (ej: 'Cra 15 #85-20')",
    )
    ubicacionDetalle: Optional[str] = Field(
        None,
        description="Barrio o zona con distancia (ej: 'Chapinero')",
    )
    precio: Optional[float] = Field(
        None,
        gt=0,
        description="Tarifa acordada o base (si se omite toma la tarifa del servicio)",
    )


class SolicitudOut(BaseModel):
    """Datos de salida al consultar solicitudes para la app del Handyman y Cliente."""

    id: str
    servicioId: str
    servicioTitulo: Optional[str] = None
    clienteId: str
    clienteNombre: Optional[str] = None
    handymanId: str
    mensaje: str
    direccion: Optional[str] = None
    ubicacionDetalle: Optional[str] = None
    precio: Optional[float] = None
    estado: EstadoSolicitud
    creado: Optional[str] = None


class CambioEstadoIn(BaseModel):
    """Datos para avanzar el estado del trabajo."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"estado": "en_camino"}}
    )

    estado: EstadoSolicitud = Field(
        ...,
        description="Nuevo estado de la solicitud ('aceptada', 'en_camino', 'en_curso', 'completada', 'rechazada')",
    )
