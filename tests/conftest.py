"""
Configuración de pytest: fixtures y mocks globales.

Estrategia de mocking:
- firebase_admin y auth.verify_id_token se mockean a nivel de módulo
  para que la app arranque sin credenciales reales.
- Firestore se reemplaza con un diccionario en memoria (FakeFirestore)
  que simula la API del cliente real.
- DeepFace nunca se importa en tests; se mockea donde se usa.
- verify_id_token usa el prefijo del token para identificar al usuario,
  permitiendo que múltiples "usuarios" coexistan en el mismo test.
"""
import io
import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


# ── FakeFirestore: simulación en memoria ─────────────────────────────────────

class FakeDocument:
    """Simula un DocumentSnapshot de Firestore."""

    def __init__(self, id: str, data: dict | None = None, ref=None):
        self.id = id
        self._data = data
        self.exists = data is not None
        self.reference = ref

    def to_dict(self):
        return dict(self._data) if self._data else {}


class FakeDocRef:
    """Simula una referencia a documento de Firestore."""

    def __init__(self, coleccion: "FakeCollection", doc_id: str):
        self._col = coleccion
        self.id = doc_id
        self._subcollections: dict[str, "FakeCollection"] = {}

    def get(self) -> FakeDocument:
        data = self._col._docs.get(self.id)
        return FakeDocument(id=self.id, data=data, ref=self)

    def set(self, data: dict):
        self._col._docs[self.id] = dict(data)

    def update(self, data: dict):
        existing = dict(self._col._docs.get(self.id, {}))
        existing.update(data)
        self._col._docs[self.id] = existing

    def delete(self):
        self._col._docs.pop(self.id, None)

    def collection(self, name: str) -> "FakeCollection":
        """Devuelve una subcolección (simula la jerarquía de Firestore)."""
        if name not in self._subcollections:
            self._subcollections[name] = FakeCollection()
        return self._subcollections[name]


class FakeQuery:
    """Simula un query de Firestore con where/order_by/limit/stream."""

    def __init__(self, coleccion: "FakeCollection", filtros: list):
        self._col = coleccion
        self._filtros = list(filtros)
        self._limit_n = None

    def where(self, campo, op, valor):
        self._filtros.append((campo, op, valor))
        return self

    def order_by(self, campo):
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def start_after(self, doc):
        return self

    def stream(self):
        resultados = []
        for doc_id, data in self._col._docs.items():
            coincide = all(data.get(c) == v for c, op, v in self._filtros if op == "==")
            if coincide:
                ref = self._col.document(doc_id)
                resultados.append(FakeDocument(id=doc_id, data=data, ref=ref))
        if self._limit_n:
            resultados = resultados[:self._limit_n]
        return resultados


class FakeCollection:
    """Simula una colección de Firestore con operaciones básicas."""

    def __init__(self):
        self._docs: dict[str, dict] = {}
        self._next_id = 1
        self._refs: dict[str, FakeDocRef] = {}

    def document(self, doc_id: str | None = None) -> FakeDocRef:
        if doc_id is None:
            doc_id = f"auto_{self._next_id}"
            self._next_id += 1
        if doc_id not in self._refs:
            self._refs[doc_id] = FakeDocRef(self, doc_id)
        return self._refs[doc_id]

    def add(self, data: dict):
        doc_id = f"auto_{self._next_id}"
        self._next_id += 1
        self._docs[doc_id] = dict(data)
        ref = self.document(doc_id)
        return (None, ref)

    def stream(self):
        return [
            FakeDocument(id=k, data=v, ref=self.document(k))
            for k, v in list(self._docs.items())
        ]

    def where(self, campo, op, valor):
        return FakeQuery(self, [(campo, op, valor)])

    def order_by(self, campo):
        return FakeQuery(self, [])

    def limit(self, n):
        q = FakeQuery(self, [])
        q._limit_n = n
        return q


class FakeFirestoreClient:
    """Simula el cliente principal de Firestore."""

    def __init__(self):
        self._collections: dict[str, FakeCollection] = {}

    def collection(self, nombre: str) -> FakeCollection:
        if nombre not in self._collections:
            self._collections[nombre] = FakeCollection()
        return self._collections[nombre]

    def reset(self):
        """Limpia todos los datos entre tests."""
        self._collections.clear()


# Instancia singleton del fake DB
fake_db = FakeFirestoreClient()


# ── Mockear firebase_admin ANTES de importar la app ──────────────────────────

_firebase_mock = types.ModuleType("firebase_admin")
_firebase_mock._apps = {}
_firebase_mock.initialize_app = MagicMock()

_credentials_mock = types.ModuleType("firebase_admin.credentials")
_credentials_mock.Certificate = MagicMock(return_value="FAKE_CRED")

_auth_mock = types.ModuleType("firebase_admin.auth")

class InvalidIdTokenError(Exception):
    pass

class EmailAlreadyExistsError(Exception):
    pass

_auth_mock.InvalidIdTokenError = InvalidIdTokenError
_auth_mock.EmailAlreadyExistsError = EmailAlreadyExistsError

_AUTH_EMAILS: set[str] = set()


def _create_user_fake(*, email: str, password: str, **kwargs):
    if email in _AUTH_EMAILS:
        raise EmailAlreadyExistsError("already exists")
    _AUTH_EMAILS.add(email)
    uid = f"uid-auth-{len(_AUTH_EMAILS):03d}"
    return types.SimpleNamespace(uid=uid, email=email)


_auth_mock.create_user = _create_user_fake

_firestore_mock_mod = types.ModuleType("firebase_admin.firestore")
_firestore_mock_mod.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"
_firestore_mock_mod.client = MagicMock(return_value=fake_db)

sys.modules["firebase_admin"] = _firebase_mock
sys.modules["firebase_admin.credentials"] = _credentials_mock
sys.modules["firebase_admin.auth"] = _auth_mock
sys.modules["firebase_admin.firestore"] = _firestore_mock_mod

# Mockear deepface
_deepface_mock = types.ModuleType("deepface")
_deepface_mock.DeepFace = MagicMock()
sys.modules["deepface"] = _deepface_mock


# ── Registro de usuarios de prueba ────────────────────────────────────────────
_TOKEN_REGISTRY: dict[str, dict] = {}


def _verify_id_token_fake(token: str) -> dict:
    """Implementación fake de verify_id_token buscando en _TOKEN_REGISTRY."""
    if token in _TOKEN_REGISTRY:
        return _TOKEN_REGISTRY[token]
    raise Exception(f"Token no reconocido: {token}")


_auth_mock.verify_id_token = _verify_id_token_fake


def _registrar_usuario(uid: str, rol: str, identidad_verificada: bool = False):
    """Registra un usuario en el fake db y en el token registry."""
    fake_db.collection("users").document(uid).set({
        "nombre": f"Usuario {rol.capitalize()}",
        "email": f"{uid}@test.com",
        "rol": rol,
        "identidadVerificada": identidad_verificada,
    })
    token = f"fake-token-{uid}"
    _TOKEN_REGISTRY[token] = {"uid": uid, "email": f"{uid}@test.com"}
    return token


def _get_app():
    """Importa y asegura que app y dependencies usan fake_db."""
    import app.firebase as fb_module
    fb_module.db = fake_db
    import app.dependencies as dep_module
    dep_module.db = fake_db
    import app.routers.usuarios as u_module
    u_module.db = fake_db
    import app.routers.servicios as s_module
    s_module.db = fake_db
    import app.routers.solicitudes as sol_module
    sol_module.db = fake_db
    import app.routers.identidad as id_module
    id_module.db = fake_db

    from app.config import settings
    settings.firebase_web_api_key = ""
    from app.main import app
    return app


# ── Fixtures de pytest ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def limpiar_db():
    """Limpia la base de datos falsa y el registry de tokens antes de cada test."""
    fake_db.reset()
    _TOKEN_REGISTRY.clear()
    _AUTH_EMAILS.clear()
    yield
    fake_db.reset()
    _TOKEN_REGISTRY.clear()
    _AUTH_EMAILS.clear()


def _hacer_cliente(uid: str, rol: str, identidad_verificada: bool = False):
    """Crea un TestClient con un usuario pre-autenticado."""
    token = _registrar_usuario(uid, rol, identidad_verificada)
    app_instance = _get_app()
    client = TestClient(app_instance, raise_server_exceptions=False)
    client._uid = uid
    client._headers = {"Authorization": f"Bearer {token}"}
    return client


@pytest.fixture
def cliente_usuario():
    return _hacer_cliente("uid-cliente-001", "cliente")


@pytest.fixture
def handyman_verificado():
    return _hacer_cliente("uid-handyman-001", "handyman", identidad_verificada=True)


@pytest.fixture
def handyman_no_verificado():
    return _hacer_cliente("uid-handyman-002", "handyman", identidad_verificada=False)


@pytest.fixture
def admin_usuario():
    return _hacer_cliente("uid-admin-001", "admin")


@pytest.fixture
def sin_token():
    app_instance = _get_app()
    return TestClient(app_instance, raise_server_exceptions=False)


def imagen_fake(contenido: bytes = b"fake-image-data", content_type: str = "image/jpeg"):
    return ("selfie.jpg", io.BytesIO(contenido), content_type)
