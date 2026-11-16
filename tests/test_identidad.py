"""
Tests para los endpoints de identidad facial:
  - POST /identidad/registrar-rostro
  - POST /identidad/validar-rostro
  - DELETE /identidad/rostro
  - Rate limiting (429)
"""
import io
import pytest
from unittest.mock import MagicMock, patch
from tests.conftest import fake_db, imagen_fake


def _imagen_bytes(size_bytes: int = 100) -> bytes:
    """Genera bytes de imagen falsos del tamaño indicado."""
    return b"\xff\xd8\xff" + b"X" * size_bytes  # emula cabecera JPEG


class TestRegistrarRostro:
    def test_registro_exitoso_con_consentimiento(self, handyman_verificado):
        """Registro exitoso cuando hay consentimiento y DeepFace devuelve verified=True."""
        with patch("app.routers.identidad.comparar_rostros_bytes") as mock_comp:
            mock_comp.return_value = {"verificado": True, "distancia": 0.20}
            with patch("app.routers.identidad.calcular_embedding") as mock_emb:
                mock_emb.return_value = [0.1] * 128

                resp = handyman_verificado.post(
                    "/identidad/registrar-rostro",
                    data={"consentimiento": "true"},
                    files={
                        "selfie": ("selfie.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
                        "documento": ("doc.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
                    },
                    headers=handyman_verificado._headers,
                )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verificar que se guardó el embedding en Firestore
        uid = handyman_verificado._uid
        bio_doc = (
            fake_db.collection("users").document(uid)
                   .collection("biometria").document("facial").get()
        )
        assert bio_doc.exists
        assert len(bio_doc.to_dict().get("embedding", [])) == 128

    def test_sin_consentimiento_devuelve_400(self, handyman_verificado):
        """Sin consentimiento=true se rechaza con 400."""
        resp = handyman_verificado.post(
            "/identidad/registrar-rostro",
            data={"consentimiento": "false"},
            files={
                "selfie": ("selfie.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
                "documento": ("doc.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
            },
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 400
        assert "consentimiento" in resp.json()["detail"].lower()

    def test_rostros_no_coinciden_devuelve_422(self, handyman_verificado):
        """Si DeepFace dice verified=False, se rechaza con 422."""
        with patch("app.routers.identidad.comparar_rostros_bytes") as mock_comp:
            mock_comp.return_value = {"verificado": False, "distancia": 0.75}

            resp = handyman_verificado.post(
                "/identidad/registrar-rostro",
                data={"consentimiento": "true"},
                files={
                    "selfie": ("selfie.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
                    "documento": ("doc.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
                },
                headers=handyman_verificado._headers,
            )
        assert resp.status_code == 422

    def test_imagen_muy_grande_devuelve_413(self, handyman_verificado):
        """Imagen que supera 5 MB devuelve 413."""
        from app.config import settings
        datos_grandes = b"X" * (settings.max_imagen_bytes + 1)

        resp = handyman_verificado.post(
            "/identidad/registrar-rostro",
            data={"consentimiento": "true"},
            files={
                "selfie": ("selfie.jpg", io.BytesIO(datos_grandes), "image/jpeg"),
                "documento": ("doc.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
            },
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 413

    def test_tipo_imagen_invalido_devuelve_400(self, handyman_verificado):
        """Un gif o pdf como imagen devuelve 400."""
        resp = handyman_verificado.post(
            "/identidad/registrar-rostro",
            data={"consentimiento": "true"},
            files={
                "selfie": ("selfie.gif", io.BytesIO(_imagen_bytes()), "image/gif"),
                "documento": ("doc.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
            },
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 400

    def test_cliente_no_puede_registrar_rostro(self, cliente_usuario):
        """Solo handyman puede registrar rostro."""
        resp = cliente_usuario.post(
            "/identidad/registrar-rostro",
            data={"consentimiento": "true"},
            files={
                "selfie": ("selfie.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
                "documento": ("doc.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
            },
            headers=cliente_usuario._headers,
        )
        assert resp.status_code == 403


class TestValidarRostro:
    def _registrar_embedding(self, uid: str, embedding: list):
        """Helper: guarda embedding directamente en fake_db."""
        fake_db.collection("users").document(uid) \
               .collection("biometria").document("facial") \
               .set({"embedding": embedding, "modelo": "Facenet", "consentimiento": True})

    def test_validacion_exitosa_rostro_coincide(self, handyman_verificado):
        """Selfie que coincide con embedding guardado → coincide=True."""
        embedding_base = [0.5] * 128
        self._registrar_embedding(handyman_verificado._uid, embedding_base)

        with patch("app.routers.identidad.calcular_embedding") as mock_emb:
            # Mismo vector → distancia coseno = 0
            mock_emb.return_value = embedding_base

            resp = handyman_verificado.post(
                "/identidad/validar-rostro",
                files={"selfie": ("selfie.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg")},
                headers=handyman_verificado._headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["coincide"] is True
        assert data["distancia"] < 0.40

    def test_validacion_fallida_rostro_diferente(self, handyman_verificado):
        """Selfie con vector muy diferente → coincide=False."""
        embedding_base = [1.0] + [0.0] * 127
        self._registrar_embedding(handyman_verificado._uid, embedding_base)

        with patch("app.routers.identidad.calcular_embedding") as mock_emb:
            # Vector opuesto → distancia coseno ~ 1.0
            mock_emb.return_value = [-1.0] + [0.0] * 127

            resp = handyman_verificado.post(
                "/identidad/validar-rostro",
                files={"selfie": ("selfie.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg")},
                headers=handyman_verificado._headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["coincide"] is False
        assert data["distancia"] > 0.40

    def test_sin_embedding_guardado_devuelve_404(self, handyman_verificado):
        """Si no hay embedding registrado, devuelve 404."""
        resp = handyman_verificado.post(
            "/identidad/validar-rostro",
            files={"selfie": ("selfie.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg")},
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 404


class TestBorrarRostro:
    def test_borrar_datos_biometricos(self, handyman_verificado):
        """DELETE /identidad/rostro elimina la biometría y resetea identidadVerificada."""
        uid = handyman_verificado._uid
        # Agregar datos biométricos previos
        fake_db.collection("users").document(uid) \
               .collection("biometria").document("facial") \
               .set({"embedding": [0.1] * 128, "modelo": "Facenet"})

        resp = handyman_verificado.delete(
            "/identidad/rostro",
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verificar que identidadVerificada se reseteó
        user_data = fake_db.collection("users").document(uid).get().to_dict()
        assert user_data.get("identidadVerificada") is False

    def test_cliente_puede_borrar_su_biometria(self, cliente_usuario):
        """Cualquier rol puede solicitar borrar sus propios datos (derecho de supresión)."""
        resp = cliente_usuario.delete(
            "/identidad/rostro",
            headers=cliente_usuario._headers,
        )
        # No hay datos que borrar, pero no debe fallar
        assert resp.status_code == 200


class TestRateLimiting:
    def test_6to_intento_devuelve_429(self, handyman_verificado):
        """Superar el límite de 5 intentos por hora devuelve 429."""
        from app.config import settings

        # Simular que ya hay 5 intentos en esta hora
        from datetime import datetime, timezone
        hora_actual = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        fake_db.collection("users").document(handyman_verificado._uid).update({
            "intentosFaciales": {
                "contador": settings.intentos_max_por_hora,
                "hora": hora_actual.isoformat(),
            }
        })

        resp = handyman_verificado.post(
            "/identidad/registrar-rostro",
            data={"consentimiento": "true"},
            files={
                "selfie": ("selfie.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
                "documento": ("doc.jpg", io.BytesIO(_imagen_bytes()), "image/jpeg"),
            },
            headers=handyman_verificado._headers,
        )
        assert resp.status_code == 429
        assert "límite" in resp.json()["detail"].lower()
