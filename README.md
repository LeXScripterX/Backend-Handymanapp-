# Handyman API — Backend

Backend FastAPI del marketplace universitario **Handyman Apps**, que conecta handymen (oficios varios) con clientes. Se consume desde una app Ionic/Angular con Capacitor.

## Tecnologías

| Capa | Tecnología |
|------|-----------|
| API | FastAPI 0.100+ |
| Auth | Firebase Auth (Google + email/contraseña) |
| Base de datos | Firestore (plan Spark) |
| Reconocimiento facial | DeepFace + Facenet (Python 3.11/3.12) |
| Huella dactilar | Solo en cliente — plugin Capacitor Biometrics (sin backend) |

---

## Requisitos previos

- Python 3.14 (API principal) y Python 3.11/3.12 (para DeepFace/TensorFlow)
- Proyecto de Firebase con Auth y Firestore habilitados
- Archivo `serviceAccountKey.json` descargado desde la consola de Firebase

---

## Instalación

### 1. Clonar e instalar dependencias base

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Dependencias de Machine Learning (venv separado con Python 3.11)

DeepFace y TensorFlow **no** son compatibles con Python 3.14. Instálalas en un venv separado:

```bash
python3.11 -m venv .venv-ml
source .venv-ml/bin/activate
pip install -r requirements_ml.txt
```

> El backend arranca normalmente sin DeepFace. El import es perezoso y solo ocurre cuando se llama a los endpoints de identidad facial.

### 3. Variables de entorno

```bash
cp .env.example .env
# Editar .env con tus valores reales
```

Parámetros disponibles en `.env`:

| Variable | Descripción | Defecto |
|----------|-------------|---------|
| `SERVICE_ACCOUNT_PATH` | Ruta al JSON de credenciales Firebase | `serviceAccountKey.json` |
| `CORS_ORIGINS` | Orígenes CORS permitidos (JSON array) | localhost:8100, capacitor://localhost |
| `UMBRAL_FACIAL` | Umbral de distancia coseno para validación facial | `0.40` |
| `MAX_IMAGEN_BYTES` | Tamaño máximo de imagen en bytes | `5242880` (5 MB) |
| `INTENTOS_MAX_POR_HORA` | Intentos de verificación facial por usuario/hora | `5` |

### 4. Reglas de seguridad Firestore

Desplegar el archivo `firestore.rules` desde la consola de Firebase o con la CLI:

```bash
firebase deploy --only firestore:rules
```

---

## Correr el servidor

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Documentación interactiva disponible en: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Correr las pruebas

```bash
source .venv/bin/activate
pytest tests/ -v --tb=short
```

Los tests **no requieren** Firebase real ni DeepFace instalado; todo se mockea en `tests/conftest.py`.

---

## Tabla de Endpoints

### Usuarios

| Método | Ruta | Rol requerido | Descripción |
|--------|------|--------------|-------------|
| `POST` | `/usuarios/registro` | Autenticado (cualquier) | Crear perfil de usuario |

### Servicios

| Método | Ruta | Rol requerido | Descripción |
|--------|------|--------------|-------------|
| `POST` | `/servicios/` | `handyman` (verificado) | Publicar un nuevo servicio |
| `GET` | `/servicios/` | Cualquier autenticado | Listar servicios (filtro por categoría, paginación) |
| `GET` | `/servicios/{id}` | Cualquier autenticado | Obtener un servicio por ID |
| `PUT` | `/servicios/{id}` | Dueño (`handyman`) o `admin` | Actualizar un servicio |
| `DELETE` | `/servicios/{id}` | Dueño (`handyman`) o `admin` | Eliminar un servicio |

**Query params para `GET /servicios/`:**
- `categoria` — filtrar por categoría (ej. `electricidad`, `plomería`, …)
- `limit` — cantidad de resultados (1–100, defecto 20)
- `cursor` — ID del último servicio visto (paginación cursor-based)

### Solicitudes

| Método | Ruta | Rol requerido | Descripción |
|--------|------|--------------|-------------|
| `POST` | `/solicitudes/` | `cliente` | Crear solicitud a un servicio |
| `GET` | `/solicitudes/` | Cualquier autenticado | Listar solicitudes propias |
| `GET` | `/solicitudes/{id}` | Participante o `admin` | Ver una solicitud específica |
| `PATCH` | `/solicitudes/{id}/estado` | Participante o `admin` | Cambiar estado de solicitud |

**Estados y transiciones:**

```
pendiente ──→ aceptada  (handyman / admin)
          ──→ rechazada (handyman / admin)
aceptada  ──→ completada (handyman / cliente / admin)
rechazada → [estado terminal]
completada → [estado terminal]
```

### Identidad Facial

| Método | Ruta | Rol requerido | Descripción |
|--------|------|--------------|-------------|
| `POST` | `/identidad/registrar-rostro` | `handyman` | Registrar embedding facial (verifica con documento) |
| `POST` | `/identidad/validar-rostro` | `handyman` | Validar selfie contra embedding guardado |
| `DELETE` | `/identidad/rostro` | Cualquier autenticado | Borrar datos biométricos propios |
| `POST` | `/identidad/verificar` | `handyman` | ⚠️ **Deprecado** — usa `/registrar-rostro` |

**Notas de identidad:**
- Se exige campo `consentimiento=true` en el formulario de registro.
- **Nunca** se guarda la imagen; solo el vector de embedding (128 floats).
- Límite: 5 intentos por hora por usuario (429 si se supera).
- Imágenes: solo `image/jpeg` o `image/png`, máximo 5 MB.

### Estado

| Método | Ruta | Rol requerido | Descripción |
|--------|------|--------------|-------------|
| `GET` | `/` | Ninguno | Health check |

---

## Estructura del proyecto

```
Backend/
├── app/
│   ├── main.py              # FastAPI, CORS, routers, manejadores de error
│   ├── config.py            # Configuración con pydantic-settings
│   ├── firebase.py          # Inicialización Admin SDK
│   ├── dependencies.py      # token_valido, usuario_actual, requiere_rol
│   ├── exceptions.py        # HandymanException + manejador global
│   ├── routers/
│   │   ├── usuarios.py      # POST /usuarios/registro
│   │   ├── servicios.py     # CRUD /servicios
│   │   ├── solicitudes.py   # CRUD /solicitudes + máquina de estados
│   │   └── identidad.py     # /identidad/registrar-rostro, validar-rostro, DELETE
│   ├── schemas/
│   │   ├── __init__.py      # Re-exportaciones
│   │   ├── servicio.py      # ServicioIn, ServicioOut
│   │   ├── usuario.py       # RegistroIn, RegistroOut
│   │   └── solicitud.py     # SolicitudIn, SolicitudOut, CambioEstadoIn
│   └── services/
│       └── facial.py        # comparar_rostros, calcular_embedding, distancia_coseno
├── tests/
│   ├── conftest.py          # Fixtures, FakeFirestore, mocks de Firebase y DeepFace
│   ├── test_usuarios.py
│   ├── test_servicios.py
│   ├── test_solicitudes.py
│   └── test_identidad.py
├── firestore.rules          # Reglas de seguridad Firestore
├── requirements.txt         # Dependencias principales (Python 3.14+)
├── requirements_ml.txt      # DeepFace + TF (Python 3.11/3.12)
├── .env.example             # Plantilla de variables de entorno
└── .gitignore               # serviceAccountKey.json y .env excluidos
```

---

## Seguridad

- `serviceAccountKey.json` y `.env` están en `.gitignore` y **nunca** deben commitearse.
- Las reglas de `firestore.rules` bloquean toda escritura directa del cliente a Firestore.
- Los campos `identidadVerificada` y `rol` solo los modifica el backend (Admin SDK).
- La subcolección `users/{uid}/biometria/**` es completamente inaccesible desde el cliente.
- Las imágenes se procesan en archivos temporales que se eliminan en bloques `try/finally`.
- El logger nunca registra uid, email, ni datos de imágenes.

---

## Huella dactilar

Las huellas dactilares **no** se procesan ni almacenan en el backend. La autenticación biométrica local (huella/face ID) se maneja exclusivamente con el plugin `@capacitor-community/biometric-auth` en la app Ionic, que desbloquea la sesión localmente sin exponer los datos biométricos a ningún servidor.
