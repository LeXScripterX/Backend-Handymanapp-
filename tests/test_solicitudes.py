"""
Tests para el router de solicitudes: flujo de estados y control de acceso por rol.
"""
import pytest
from tests.conftest import fake_db

SERVICIO_BASE = {
    "titulo": "Reparación de tubería urgente",
    "descripcion": "Servicio de gasfitería 24/7",
    "precio": 200.0,
    "categoria": "gasfitería",
}


def _setup_servicio(handyman_client) -> str:
    """Crea un servicio y retorna su ID."""
    resp = handyman_client.post(
        "/servicios/",
        json=SERVICIO_BASE,
        headers=handyman_client._headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _crear_solicitud(cliente_client, servicio_id: str) -> str:
    """Crea una solicitud y retorna su ID."""
    resp = cliente_client.post(
        "/solicitudes/",
        json={"servicioId": servicio_id, "mensaje": "Necesito ayuda urgente con la tubería"},
        headers=cliente_client._headers,
    )
    assert resp.status_code == 201, f"Error al crear solicitud: {resp.json()}"
    return resp.json()["id"]


class TestCrearSolicitud:
    def test_cliente_puede_crear_solicitud(self, handyman_verificado, cliente_usuario):
        servicio_id = _setup_servicio(handyman_verificado)
        resp = cliente_usuario.post(
            "/solicitudes/",
            json={"servicioId": servicio_id, "mensaje": "Necesito ayuda con la tubería rota"},
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    def test_handyman_no_puede_crear_solicitud(self, handyman_verificado):
        servicio_id = _setup_servicio(handyman_verificado)
        resp = handyman_verificado.post(
            "/solicitudes/",
            json={"servicioId": servicio_id, "mensaje": "Solicitando mi propio servicio"},
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 403

    def test_servicio_inexistente_devuelve_404(self, cliente_usuario):
        resp = cliente_usuario.post(
            "/solicitudes/",
            json={"servicioId": "no-existe-999", "mensaje": "Mensaje de prueba para el test"},
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 404

    def test_mensaje_corto_rechazado(self, handyman_verificado, cliente_usuario):
        servicio_id = _setup_servicio(handyman_verificado)
        resp = cliente_usuario.post(
            "/solicitudes/",
            json={"servicioId": servicio_id, "mensaje": "Corto"},  # < 10 chars
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 422


class TestListarSolicitudes:
    def test_cliente_ve_solo_sus_solicitudes(self, handyman_verificado, cliente_usuario):
        servicio_id = _setup_servicio(handyman_verificado)
        _crear_solicitud(cliente_usuario, servicio_id)

        resp = cliente_usuario.get("/solicitudes/", headers=cliente_usuario._headers)
        assert resp.status_code == 200
        solicitudes = resp.json()
        for s in solicitudes:
            assert s["clienteId"] == cliente_usuario._uid

    def test_handyman_ve_solo_las_dirigidas_a_el(self, handyman_verificado, cliente_usuario):
        servicio_id = _setup_servicio(handyman_verificado)
        _crear_solicitud(cliente_usuario, servicio_id)

        resp = handyman_verificado.get("/solicitudes/", headers=handyman_verificado._headers)
        assert resp.status_code == 200
        solicitudes = resp.json()
        for s in solicitudes:
            assert s["handymanId"] == handyman_verificado._uid


class TestCambiarEstado:
    def test_handyman_acepta_solicitud_pendiente(self, handyman_verificado, cliente_usuario):
        servicio_id = _setup_servicio(handyman_verificado)
        sol_id = _crear_solicitud(cliente_usuario, servicio_id)

        resp = handyman_verificado.patch(
            f"/solicitudes/{sol_id}/estado",
            json={"estado": "aceptada"},
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 200
        assert resp.json()["estado"] == "aceptada"

    def test_handyman_rechaza_solicitud_pendiente(self, handyman_verificado, cliente_usuario):
        servicio_id = _setup_servicio(handyman_verificado)
        sol_id = _crear_solicitud(cliente_usuario, servicio_id)

        resp = handyman_verificado.patch(
            f"/solicitudes/{sol_id}/estado",
            json={"estado": "rechazada"},
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 200
        assert resp.json()["estado"] == "rechazada"

    def test_cliente_no_puede_aceptar_solicitud(self, handyman_verificado, cliente_usuario):
        """El cliente no puede mover una solicitud de pendiente a aceptada."""
        servicio_id = _setup_servicio(handyman_verificado)
        sol_id = _crear_solicitud(cliente_usuario, servicio_id)

        resp = cliente_usuario.patch(
            f"/solicitudes/{sol_id}/estado",
            json={"estado": "aceptada"},
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 422  # transición no permitida

    def test_flujo_completo_pendiente_aceptada_completada(
        self, handyman_verificado, cliente_usuario
    ):
        """Flujo completo: pendiente → aceptada → completada."""
        servicio_id = _setup_servicio(handyman_verificado)
        sol_id = _crear_solicitud(cliente_usuario, servicio_id)

        # Handyman acepta
        r1 = handyman_verificado.patch(
            f"/solicitudes/{sol_id}/estado",
            json={"estado": "aceptada"},
            headers=handyman_verificado._headers,
        )
        assert r1.status_code == 200

        # Handyman completa
        r2 = handyman_verificado.patch(
            f"/solicitudes/{sol_id}/estado",
            json={"estado": "completada"},
            headers=handyman_verificado._headers,
        )
        assert r2.status_code == 200
        assert r2.json()["estado"] == "completada"

    def test_estado_rechazado_es_terminal(self, handyman_verificado, cliente_usuario):
        """Una solicitud rechazada no puede cambiar de estado."""
        servicio_id = _setup_servicio(handyman_verificado)
        sol_id = _crear_solicitud(cliente_usuario, servicio_id)

        handyman_verificado.patch(
            f"/solicitudes/{sol_id}/estado",
            json={"estado": "rechazada"},
            headers=handyman_verificado._headers,
        )

        resp = handyman_verificado.patch(
            f"/solicitudes/{sol_id}/estado",
            json={"estado": "aceptada"},
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 422

    def test_tercero_no_puede_ver_solicitud(self, handyman_verificado, cliente_usuario):
        """Un usuario que no participa en la solicitud no puede verla."""
        from tests.conftest import _hacer_cliente

        servicio_id = _setup_servicio(handyman_verificado)
        sol_id = _crear_solicitud(cliente_usuario, servicio_id)

        tercero = _hacer_cliente("uid-tercero-001", "cliente", identidad_verificada=False)
        resp = tercero.get(
            f"/solicitudes/{sol_id}",
            headers=tercero._headers,
        )
        assert resp.status_code == 403
