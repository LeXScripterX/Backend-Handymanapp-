import sys
import requests

API_KEY = "AIzaSyCRfqV0mLMAgYTV7dWBegDagvoKfZwStT4"
EMAIL = sys.argv[1] if len(sys.argv) > 1 else "admin@handymanapp.com"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "admin123"

r = requests.post(
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}",
    json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True},
)
d = r.json()
print("email:", EMAIL)
if "idToken" in d:
    print("uid:", d.get("localId"))
    print(d["idToken"])
else:
    print(d)