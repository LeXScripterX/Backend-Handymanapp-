"""
Manejador global de excepciones y logging sin datos personales.
"""
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ── Configuración del logger ──────────────────────────────────────────────────
# Formato sin uid, email ni datos sensibles
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("handyman")


# ── Excepción base de la aplicación ──────────────────────────────────────────
class HandymanException(Exception):
    """Excepción base con código HTTP y mensaje controlado."""

    def __init__(self, status_code: int, detail: str, code: str = "ERROR"):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)


# ── Registro de manejadores en la app ─────────────────────────────────────────
def registrar_manejadores(app: FastAPI) -> None:
    """Registra los manejadores de excepciones globales en la app FastAPI."""

    @app.exception_handler(HandymanException)
    async def handyman_exception_handler(
        request: Request, exc: HandymanException
    ) -> JSONResponse:
        """Convierte HandymanException a respuesta JSON consistente."""
        logger.warning("HandymanException [%s] %s — %s", exc.code, exc.status_code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    @app.exception_handler(Exception)
    async def excepcion_generica_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Captura cualquier excepción no manejada y devuelve 500 sin exponer
        información interna ni datos personales.
        """
        # Loguea el stack trace completo para debugging interno
        logger.error(
            "Error no manejado en %s %s: %s",
            request.method,
            request.url.path,   # solo path, NO query params (podrían tener datos)
            type(exc).__name__,
        )
        logger.debug("Stack trace: %s", traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Error interno del servidor",
                "code": "INTERNAL_ERROR",
            },
        )
