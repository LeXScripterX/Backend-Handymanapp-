"""
Esquemas Pydantic para servicios.
"""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

# Categorías válidas de servicios en el marketplace
CategoriaServicio = Literal[
    "electricidad",
    "plomería",
    "carpintería",
    "pintura",
    "limpieza",
    "jardinería",
    "gasfitería",
    "otro",
]


class ServicioIn(BaseModel):
    """Datos de entrada para crear o actualizar un servicio."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "titulo": "Reparación eléctrica residencial",
                "descripcion": "Instalación y arreglo de tomas, breakers e iluminación.",
                "precio": 45000,
                "categoria": "electricidad",
            }
        }
    )

    titulo: str = Field(
        ...,
        min_length=3,
        max_length=80,
        description="Título del servicio (3 a 80 caracteres)",
    )
    descripcion: str = Field(
        ...,
        max_length=500,
        description="Descripción detallada del servicio (máx. 500 caracteres)",
    )
    precio: float = Field(
        ...,
        gt=0,
        description="Precio del servicio (debe ser mayor a 0)",
    )
    categoria: CategoriaServicio = Field(
        ...,
        description="Categoría del servicio",
    )


class ServicioOut(BaseModel):
    """Datos de salida al consultar un servicio."""

    id: str
    titulo: str
    descripcion: str
    precio: float
    categoria: str
    handymanId: str
    activo: Optional[bool] = True
