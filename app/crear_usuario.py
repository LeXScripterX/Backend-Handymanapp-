import sys
import requests

API_KEY = "AIzaSyCRfqV0mLMAgYTV7dWBegDagvoKfZwStT4"
EMAIL = sys.argv[1] if len(sys.argv) > 1 else "prueba@correo.com"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "prueba123"

r = requests.post(
    f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}",
    json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True},
)
data = r.json()
print("email:", EMAIL)
print(data.get("idToken") or data)