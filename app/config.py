"""
Configuración centralizada de la aplicación usando pydantic-settings.
Los valores se leen desde el archivo .env (o variables de entorno del sistema).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ruta al archivo de credenciales de Firebase Admin SDK
    service_account_path: str = "serviceAccountKey.json"

    # Orígenes permitidos para CORS (separados por comas en el .env)
    cors_origins: list[str] = [
        "http://localhost:8100",
        "capacitor://localhost",
        "http://localhost",
    ]

    # Umbral de distancia coseno para validación facial (0.0 = idéntico, 1.0 = totalmente diferente)
    umbral_facial: float = 0.40

    # Tamaño máximo de imagen en bytes (5 MB por defecto)
    max_imagen_bytes: int = 5 * 1024 * 1024  # 5 MB

    # Número máximo de intentos de verificación facial por usuario por hora
    intentos_max_por_hora: int = 5

    # API key web de Firebase (Identity Toolkit). Sirve para devolver idToken al crear cuenta desde Swagger.
    firebase_web_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Permite pasar cors_origins como JSON array en .env
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Devuelve la instancia singleton de configuración (cacheada)."""
    return Settings()


# Instancia global para importar directamente
settings = get_settings()
