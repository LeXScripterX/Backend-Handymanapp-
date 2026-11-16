"""
Tests para el router de servicios: CRUD completo y control de acceso por rol.
"""
import pytest
from tests.conftest import fake_db

# Payload base válido para crear un servicio
SERVICIO_VALIDO = {
    "titulo": "Instalación eléctrica domiciliaria",
    "descripcion": "Instalación de enchufes, breakers y cableado.",
    "precio": 150.0,
    "categoria": "electricidad",
}


def _crear_servicio(client, headers) -> str:
    """Helper: crea un servicio y retorna su ID."""
    resp = client.post("/servicios/", json=SERVICIO_VALIDO, headers=headers)
    assert resp.status_code == 201, f"Fallo al crear servicio: {resp.json()}"
    return resp.json()["id"]


class TestCrearServicio:
    def test_handyman_verificado_puede_crear(self, handyman_verificado):
        resp = handyman_verificado.post(
            "/servicios/",
            json=SERVICIO_VALIDO,
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    def test_handyman_no_verificado_recibe_403(self, handyman_no_verificado):
        resp = handyman_no_verificado.post(
            "/servicios/",
            json=SERVICIO_VALIDO,
            headers=handyman_no_verificado._headers,
        )
        assert resp.status_code == 403

    def test_cliente_no_puede_crear(self, cliente_usuario):
        resp = cliente_usuario.post(
            "/servicios/",
            json=SERVICIO_VALIDO,
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 403

    def test_titulo_corto_rechazado(self, handyman_verificado):
        payload = {**SERVICIO_VALIDO, "titulo": "AB"}  # menos de 3 caracteres
        resp = handyman_verificado.post(
            "/servicios/",
            json=payload,
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 422

    def test_precio_negativo_rechazado(self, handyman_verificado):
        payload = {**SERVICIO_VALIDO, "precio": -10}
        resp = handyman_verificado.post(
            "/servicios/",
            json=payload,
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 422

    def test_categoria_invalida_rechazada(self, handyman_verificado):
        payload = {**SERVICIO_VALIDO, "categoria": "magia_negra"}
        resp = handyman_verificado.post(
            "/servicios/",
            json=payload,
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 422


class TestListarServicios:
    def test_cliente_puede_listar(self, handyman_verificado, cliente_usuario):
        _crear_servicio(handyman_verificado, handyman_verificado._headers)
        resp = cliente_usuario.get("/servicios/", headers=cliente_usuario._headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_filtro_por_categoria(self, handyman_verificado, cliente_usuario):
        _crear_servicio(handyman_verificado, handyman_verificado._headers)
        resp = cliente_usuario.get(
            "/servicios/?categoria=electricidad",
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 200
        for s in resp.json():
            assert s["categoria"] == "electricidad"

    def test_paginacion_limit(self, handyman_verificado, cliente_usuario):
        # Crear 3 servicios
        for i in range(3):
            payload = {**SERVICIO_VALIDO, "titulo": f"Servicio número {i + 1}"}
            handyman_verificado.post("/servicios/", json=payload, headers=handyman_verificado._headers)

        resp = cliente_usuario.get("/servicios/?limit=2", headers=cliente_usuario._headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 2


class TestObtenerServicio:
    def test_obtener_por_id(self, handyman_verificado, cliente_usuario):
        servicio_id = _crear_servicio(handyman_verificado, handyman_verificado._headers)
        resp = cliente_usuario.get(f"/servicios/{servicio_id}", headers=cliente_usuario._headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == servicio_id

    def test_id_inexistente_devuelve_404(self, cliente_usuario):
        resp = cliente_usuario.get("/servicios/no-existe", headers=cliente_usuario._headers)
        assert resp.status_code == 404


class TestActualizarServicio:
    def test_dueno_puede_actualizar(self, handyman_verificado):
        servicio_id = _crear_servicio(handyman_verificado, handyman_verificado._headers)
        payload = {**SERVICIO_VALIDO, "titulo": "Título actualizado ok"}
        resp = handyman_verificado.put(
            f"/servicios/{servicio_id}",
            json=payload,
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 200
        assert resp.json()["titulo"] == "Título actualizado ok"

    def test_otro_handyman_no_puede_actualizar(self, handyman_verificado):
        """Un segundo handyman no puede actualizar el servicio de otro."""
        from tests.conftest import _hacer_cliente
        servicio_id = _crear_servicio(handyman_verificado, handyman_verificado._headers)

        otro_client = _hacer_cliente("uid-handyman-otro", "handyman", identidad_verificada=True)
        resp = otro_client.put(
            f"/servicios/{servicio_id}",
            json={**SERVICIO_VALIDO, "titulo": "Intento de robo"},
            headers=otro_client._headers,
        )
        assert resp.status_code == 403

    def test_admin_puede_actualizar_cualquier_servicio(self, handyman_verificado, admin_usuario):
        servicio_id = _crear_servicio(handyman_verificado, handyman_verificado._headers)
        payload = {**SERVICIO_VALIDO, "titulo": "Admin actualizó esto"}
        resp = admin_usuario.put(
            f"/servicios/{servicio_id}",
            json=payload,
            headers=admin_usuario._headers,
        )
        assert resp.status_code == 200


class TestEliminarServicio:
    def test_dueno_puede_eliminar(self, handyman_verificado):
        servicio_id = _crear_servicio(handyman_verificado, handyman_verificado._headers)
        resp = handyman_verificado.delete(
            f"/servicios/{servicio_id}",
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 204

    def test_cliente_no_puede_eliminar(self, handyman_verificado, cliente_usuario):
        servicio_id = _crear_servicio(handyman_verificado, handyman_verificado._headers)
        resp = cliente_usuario.delete(
            f"/servicios/{servicio_id}",
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 403

    def test_admin_puede_eliminar_cualquier_servicio(self, handyman_verificado, admin_usuario):
        servicio_id = _crear_servicio(handyman_verificado, handyman_verificado._headers)
        resp = admin_usuario.delete(
            f"/servicios/{servicio_id}",
            headers=admin_usuario._headers,
        )
        assert resp.status_code == 204
