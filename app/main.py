"""
Punto de entrada principal de la Handyman API.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import identidad, servicios, usuarios, admin
from app.config import settings
from app.exceptions import registrar_manejadores
from app.routers import identidad, servicios, solicitudes, usuarios

app = FastAPI(
    title="Handyman API",
    description="""
Backend del marketplace universitario **Handyman Apps**.

## Cómo probar en Swagger (`/docs`)

1. Pulsa **Authorize** (candado verde) y pega el `idToken` de Firebase **sin** la palabra `Bearer`.
2. Los campos ya vienen en modo prueba: edita el JSON o los path/query y pulsa **Execute**.
3. El token se obtiene en Firebase Auth (login email/contraseña o Google) o con Identity Toolkit:

```
POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=TU_WEB_API_KEY
{"email":"...","password":"...","returnSecureToken":true}
```

Usa el campo `idToken` de la respuesta. Casi todos los endpoints exigen ese token.
""",
    version="2.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True,
        "tryItOutEnabled": True,
        "displayRequestDuration": True,
        "filter": True,
        "docExpansion": "list",
    },
)
# Compatibilidad: algunas UIs de Swagger no editan bien esquemas OpenAPI 3.1
app.openapi_version = "3.0.2"

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Manejadores de excepciones globales ───────────────────────────────────────
registrar_manejadores(app)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(usuarios.router)
app.include_router(servicios.router)
app.include_router(solicitudes.router)
app.include_router(identidad.router)
app.include_router(admin.router)

@app.get("/", tags=["Estado"])
def raiz():
    """Endpoint de salud para verificar que la API está corriendo."""
    return {"estado": "ok", "version": "2.0.0"}