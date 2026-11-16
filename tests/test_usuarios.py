"""
Tests para el router de usuarios: registro, duplicados y autenticación.
"""
import pytest
from tests.conftest import fake_db, _get_app, _registrar_usuario, _TOKEN_REGISTRY
from fastapi.testclient import TestClient


class TestRegistro:
    def test_registro_exitoso_como_cliente(self):
        """Un usuario con token válido puede registrarse como cliente."""
        # Registrar solo el token, SIN crear perfil en Firestore (el endpoint lo crea)
        uid = "uid-registro-nuevo-001"
        token = f"fake-token-{uid}"
        _TOKEN_REGISTRY[token] = {"uid": uid, "email": "nuevo@test.com"}

        client = TestClient(_get_app(), raise_server_exceptions=False)
        resp = client.post(
            "/usuarios/registro",
            json={"nombre": "Nuevo Cliente", "rol": "cliente"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert data["rol"] == "cliente"

    def test_registro_exitoso_como_handyman(self):
        """Un usuario puede registrarse como handyman."""
        uid = "uid-registro-nuevo-002"
        token = f"fake-token-{uid}"
        _TOKEN_REGISTRY[token] = {"uid": uid, "email": "hand@test.com"}

        client = TestClient(_get_app(), raise_server_exceptions=False)
        resp = client.post(
            "/usuarios/registro",
            json={"nombre": "Nuevo Handyman", "rol": "handyman"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["rol"] == "handyman"

    def test_registro_duplicado_devuelve_409(self, cliente_usuario):
        """Intentar registrarse dos veces devuelve 409 Conflict."""
        # El fixture ya creó el perfil; intentar de nuevo con el mismo uid:
        resp = cliente_usuario.post(
            "/usuarios/registro",
            json={"nombre": "Duplicado", "rol": "cliente"},
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 409

    def test_rol_admin_no_se_puede_autoasignar(self):
        """El rol 'admin' no es un valor aceptado en el registro (422 de Pydantic)."""
        uid = "uid-registro-nuevo-003"
        token = f"fake-token-{uid}"
        _TOKEN_REGISTRY[token] = {"uid": uid, "email": "a@test.com"}

        client = TestClient(_get_app(), raise_server_exceptions=False)
        resp = client.post(
            "/usuarios/registro",
            json={"nombre": "Atacante", "rol": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_sin_token_devuelve_401(self, sin_token):
        """Sin token de autorización, el registro devuelve 401."""
        resp = sin_token.post(
            "/usuarios/registro",
            json={"nombre": "Sin Token", "rol": "cliente"},
        )
        assert resp.status_code == 401


class TestCrearCuenta:
    def test_crea_auth_y_perfil_sin_token(self, sin_token):
        """Swagger puede crear un usuario nuevo sin Authorize previo."""
        resp = sin_token.post(
            "/usuarios/cuenta",
            json={
                "email": "daniiel@gmail.com",
                "password": "prueba123",
                "nombre": "Ana Pérez",
                "rol": "cliente",
                "telefono": "3001234567",
                "terminosAceptados": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert data["email"] == "daniiel@gmail.com"
        assert data["rol"] == "cliente"
        perfil = fake_db.collection("users").document(data["uid"]).get()
        assert perfil.exists
        assert perfil.to_dict()["nombre"] == "Ana Pérez"

    def test_correo_duplicado_devuelve_409(self, sin_token):
        payload = {
            "email": "repetido@gmail.com",
            "password": "prueba123",
            "nombre": "Uno",
            "rol": "cliente",
        }
        primero = sin_token.post("/usuarios/cuenta", json=payload)
        assert primero.status_code == 201
        segundo = sin_token.post("/usuarios/cuenta", json=payload)
        assert segundo.status_code == 409


class TestPerfil:
    def test_ver_perfil_handyman(self, handyman_verificado):
        """Consulta el perfil del usuario autenticado con métricas y estado."""
        resp = handyman_verificado.get("/usuarios/perfil", headers=handyman_verificado._headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["uid"] == handyman_verificado._uid
        assert data["rol"] == "handyman"
        assert data["identidadVerificada"] is True
        assert "calificacion" in data
        assert "disponible" in data

    def test_actualizar_disponibilidad_y_telefono(self, handyman_verificado):
        """El handyman puede alternar el switch de disponibilidad y editar su teléfono."""
        resp = handyman_verificado.put(
            "/usuarios/perfil",
            json={"disponible": False, "telefono": "300 123 4567"},
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["disponible"] is False
        assert data["telefono"] == "300 123 4567"

