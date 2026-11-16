"""
Inicialización de Firebase Admin SDK.
Lee la ruta del service account desde la configuración centralizada.
"""
import firebase_admin
from firebase_admin import credentials, firestore
from app.config import settings

# Solo inicializa si no hay una app ya inicializada (evita error al recargar con --reload)
if not firebase_admin._apps:
    firebase_admin.initialize_app(
        credentials.Certificate(settings.service_account_path)
    )

# db siempre se asigna, independientemente de si _apps ya existía
db = firestore.client()