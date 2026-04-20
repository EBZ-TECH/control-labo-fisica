"""
Crea o actualiza solo los usuarios de Firebase Authentication.
No usa puerto COM: úsalo si main.py falla antes por el Arduino.

Requisito: en Firebase Console → Authentication → Sign-in method,
activa "Correo electrónico/contraseña".
"""
from pathlib import Path

import firebase_admin
from firebase_admin import auth as fb_auth
from firebase_admin import credentials

BASE = Path(__file__).resolve().parent
cred = credentials.Certificate(str(BASE / "clave_firebase.json"))
firebase_admin.initialize_app(
    cred,
    {"databaseURL": "https://control-acceso-lab-default-rtdb.firebaseio.com/"},
)

CUENTAS = [
    ("estudiante@gmail.com", "123456"),
    ("admin@gmail.com", "admin123"),
]

for email, password in CUENTAS:
    try:
        u = fb_auth.get_user_by_email(email)
        fb_auth.update_user(u.uid, password=password)
        print("Actualizado:", email)
    except fb_auth.UserNotFoundError:
        fb_auth.create_user(email=email, password=password, email_verified=False)
        print("Creado:", email)
    except Exception as e:
        print("ERROR", email, "->", e)
        print("¿Activaste Correo/contraseña en Authentication → Sign-in method?")

print("\nListo. Recarga Authentication → Usuarios en la consola de Firebase.")
