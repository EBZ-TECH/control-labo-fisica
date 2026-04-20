import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import firebase_admin
import serial
from firebase_admin import auth as fb_auth
from firebase_admin import credentials, db

# ----------------------------
# FIREBASE
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "clave_firebase.json"

_svc_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
if _svc_json:
    cred = credentials.Certificate(json.loads(_svc_json))
else:
    cred = credentials.Certificate(str(CREDENTIALS_FILE))
firebase_admin.initialize_app(
    cred,
    {"databaseURL": "https://control-acceso-lab-default-rtdb.firebaseio.com/"},
)


def asegurar_usuarios_firebase_auth() -> None:
    """Crea o actualiza contraseñas en Firebase Auth (Email/contraseña)."""
    cuentas = [
        ("estudiante@gmail.com", "123456"),
        ("admin@gmail.com", "admin123"),
    ]
    for email, password in cuentas:
        try:
            u = fb_auth.get_user_by_email(email)
            fb_auth.update_user(u.uid, password=password)
            print(f"Auth: usuario {email} actualizado.", flush=True)
        except fb_auth.UserNotFoundError:
            fb_auth.create_user(email=email, password=password, email_verified=False)
            print(f"Auth: usuario {email} creado.", flush=True)
        except Exception as e:
            print(
                f"Auth: no se pudo preparar {email}: {e}\n"
                "  Activa 'Correo/contrasena' en Firebase Console: Authentication -> Sign-in method.",
                flush=True,
            )


# Antes del serial: si el COM falla y el script termina, los usuarios de Auth ya quedaron creados.
asegurar_usuarios_firebase_auth()

# ----------------------------
# SERIAL (puerto: variable SERIAL_PORT en CMD, por defecto COM7)
# ----------------------------
SERIAL_PORT = (os.environ.get("SERIAL_PORT") or "COM7").strip()
SKIP_SERIAL = os.environ.get("SKIP_SERIAL", "").strip().lower() in ("1", "true", "yes", "si")
ser = None
try:
    ser = serial.Serial(SERIAL_PORT, 9600, timeout=1)
except serial.SerialException as e:
    if SKIP_SERIAL:
        print(
            f"AVISO: sin puerto serie ({SERIAL_PORT!r}: {e}).\n"
            "  Modo prueba web: puente HTTP activo; teclas solo se registran en consola (no van al Arduino).\n"
            "  Para hardware real: cierra el Monitor serie, quita SKIP_SERIAL y usa SERIAL_PORT correcto.\n",
            flush=True,
        )
    else:
        print(
            f"No se pudo abrir el puerto serie {SERIAL_PORT!r}.\n"
            f"Detalle: {e}\n\n"
            "Qué revisar:\n"
            "  • Cierra el Monitor serie del Arduino IDE y cualquier otra ventana con main.py.\n"
            "  • En el Administrador de dispositivos confirma el número de COM del Arduino.\n"
            "  • Prueba solo web sin COM: set SKIP_SERIAL=1\n"
            "  • Si el COM no es el 7: set SERIAL_PORT=COM6\n",
            flush=True,
        )
        sys.exit(1)
if ser is not None:
    time.sleep(2)

SERIAL_LOCK = threading.Lock()

KEYPAD_CHARS = frozenset("0123456789*#")
INTER_TECLA_S = 0.22
# Render/Railway/Fly suelen definir PORT; local usa 127.0.0.1:8765 por defecto.
_PORT_ENV = os.environ.get("PORT", "").strip()
BRIDGE_PORT = int(_PORT_ENV or os.environ.get("BRIDGE_PORT", "8765"))
BRIDGE_HOST = (
    os.environ.get("BRIDGE_HOST", "").strip()
    or ("0.0.0.0" if _PORT_ENV else "127.0.0.1")
)

_web_lock = threading.Lock()
_web_role = "admin"
_web_email = ""

CMD_INVALID_LCD = b"!INVALID_USER\n"

_arduino_state_lock = threading.Lock()
_arduino_bloqueado = False
_arduino_modo = "menu"

print("Python listo.", flush=True)
print(
    "Teclado CMD -> serial (mismo que antes).\n"
    "Puente web (menu virtual) -> http://127.0.0.1:"
    + str(BRIDGE_PORT)
    + "  (desde el index, opcion 2)\n",
    flush=True,
)

if not sys.stdin.isatty():
    print(
        "\nAVISO: stdin no parece una consola interactiva. `input()` puede fallar.\n"
        "Abre CMD en fase3-python y ejecuta: python main.py\n",
        flush=True,
    )


def enviar_raw(b: bytes) -> None:
    if ser is None:
        print(f"[sin-serial] {b.decode('utf-8', errors='replace').strip()}", flush=True)
        return
    with SERIAL_LOCK:
        ser.write(b)
        ser.flush()


def enviar_tecla_a_arduino(c: str) -> None:
    with _arduino_state_lock:
        bloq = _arduino_bloqueado
    if bloq:
        print(f"[bloqueo] Tecla '{c}' no enviada (Arduino en bloqueo).", flush=True)
        return
    enviar_raw((c + "\n").encode("utf-8"))


def bucle_teclado_interactivo() -> None:
    while True:
        try:
            linea = input("key> ").strip()
            if not linea:
                continue

            limpia = "".join(ch for ch in linea if ch in KEYPAD_CHARS)
            if not limpia:
                print("  (ignorado: usa solo 0-9, * y #)", flush=True)
                continue

            if len(limpia) == 1:
                enviar_tecla_a_arduino(limpia)
            else:
                for i, ch in enumerate(limpia):
                    enviar_tecla_a_arduino(ch)
                    if i < len(limpia) - 1:
                        time.sleep(INTER_TECLA_S)

        except EOFError:
            print("\nFin de entrada (EOF). Cerrando.", flush=True)
            break
        except Exception as e:
            print(f"Error teclado: {e}", flush=True)


def buscar_reserva_por_codigo(codigo: str):
    reserva = db.reference(f"reservas/{codigo}").get()
    if isinstance(reserva, dict) and reserva:
        return reserva

    reservas = db.reference("reservas").get() or {}
    for item in reservas.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("codigo", "")).strip() == codigo:
            return item
    return None


def validar_codigo(codigo: str) -> str:
    reserva = buscar_reserva_por_codigo(codigo)

    if not reserva:
        return "INVALIDO"

    estado = str(reserva.get("estado", "")).strip().lower()
    if estado != "activo":
        return "DENEGADO"

    try:
        fecha_reserva = datetime.strptime(str(reserva["fecha"]), "%Y-%m-%d").date()
        hora_inicio_time = datetime.strptime(str(reserva["hora_inicio"]), "%H:%M").time()
        tiempo_min = int(reserva["tiempo_min"])
    except Exception as e:
        print(f"Error Firebase: {e}", flush=True)
        return "DENEGADO"

    ahora = datetime.now()

    if ahora.date() != fecha_reserva:
        return "DENEGADO"

    inicio = datetime.combine(fecha_reserva, hora_inicio_time)
    fin = inicio + timedelta(minutes=tiempo_min)

    if inicio <= ahora <= fin:
        return "OK"

    return "DENEGADO"


def escuchar_serial():
    global _arduino_bloqueado, _arduino_modo

    if ser is None:
        while True:
            time.sleep(2)
        return
    while True:
        try:
            codigo = ""
            with SERIAL_LOCK:
                if ser.in_waiting:
                    codigo = ser.readline().decode("utf-8", errors="ignore").strip()

            if codigo and codigo.isdigit() and len(codigo) == 6:
                print(f"[Arduino] Código recibido: {codigo}", flush=True)

                respuesta = validar_codigo(codigo)
                print(f"[Firebase] Respuesta: {respuesta}", flush=True)

                with SERIAL_LOCK:
                    ser.write((respuesta + "\n").encode("utf-8"))
                    ser.flush()
            elif codigo.startswith("!BLOQUEO_ON"):
                with _arduino_state_lock:
                    _arduino_bloqueado = True
                print("[Arduino] Bloqueo ON -> teclado web deshabilitado.", flush=True)
            elif codigo.startswith("!BLOQUEO_OFF"):
                with _arduino_state_lock:
                    _arduino_bloqueado = False
                print("[Arduino] Bloqueo OFF -> teclado web habilitado.", flush=True)
            elif codigo.upper().startswith("!UI:"):
                suf = codigo[4:].strip().lower()
                if suf in ("menu", "codigo"):
                    with _arduino_state_lock:
                        _arduino_modo = suf
                    print(f"[Arduino] Modo LCD -> {suf} (sync web)", flush=True)
            elif codigo:
                print(f"[Arduino] Línea ignorada: {codigo!r}", flush=True)

            time.sleep(0.1)

        except Exception as e:
            print(f"Error serial: {e}", flush=True)
            time.sleep(1)


def _rol_desde_email(email: str) -> str:
    e = (email or "").strip().lower()
    if e == "admin@gmail.com":
        return "admin"
    return "student"


class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _cors(self):
        o = (self.headers.get("Origin") or "").strip()
        local = {
            "http://127.0.0.1:8080",
            "http://localhost:8080",
            "http://127.0.0.1:5500",
            "http://localhost:5500",
        }
        extras = {x.strip() for x in os.environ.get("CORS_ORIGINS", "").split(",") if x.strip()}
        if o in local or o in extras:
            return o
        if o.endswith(".vercel.app"):
            return o
        return "*"

    def _send(self, code: int, body: str | None, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", self._cors())
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", ctype)
        self.end_headers()
        if body is not None:
            self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self):
        self._send(204, "")

    def do_GET(self):
        path = (self.path or "").split("?", 1)[0].rstrip("/") or "/"
        if path == "/status":
            with _arduino_state_lock:
                b = _arduino_bloqueado
                m = _arduino_modo
            self._send(200, json.dumps({"bloqueado": b, "modo": m}))
            return
        self._send(404, '{"error":"no_encontrado"}')

    def do_POST(self):
        global _web_role, _web_email

        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n).decode("utf-8", errors="ignore") if n else ""
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            self._send(400, '{"error":"json_invalido"}')
            return

        path = (self.path or "").split("?", 1)[0].rstrip("/") or "/"

        if path == "/session":
            email = str(data.get("email", "")).strip()
            role = str(data.get("role", "")).strip().lower()
            if role not in ("admin", "student"):
                role = _rol_desde_email(email)
            with _web_lock:
                _web_email = email
                _web_role = role
            self._send(200, '{"ok":true}')
            return

        if path == "/key":
            key = str(data.get("key", "")).strip()
            context = str(data.get("context", "menu")).strip().lower()
            if len(key) != 1 or key not in KEYPAD_CHARS:
                self._send(400, '{"error":"tecla_invalida"}')
                return

            with _arduino_state_lock:
                bloq = _arduino_bloqueado
            if bloq:
                self._send(403, '{"error":"bloqueado","bloqueado":true}')
                return

            with _web_lock:
                role = _web_role

            if role == "student" and context == "menu" and key == "2":
                enviar_raw(CMD_INVALID_LCD)
                self._send(200, '{"ok":true,"lcd":"usuario_invalido"}')
                return

            enviar_tecla_a_arduino(key)
            self._send(200, '{"ok":true}')
            return

        self._send(404, '{"error":"no_encontrado"}')


def iniciar_puente_web():
    srv = HTTPServer((BRIDGE_HOST, BRIDGE_PORT), BridgeHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    print(
        f"Puente HTTP en http://{BRIDGE_HOST}:{BRIDGE_PORT} "
        "(GET /status, POST /session, POST /key)",
        flush=True,
    )


threading.Thread(target=escuchar_serial, daemon=True).start()
iniciar_puente_web()

HEADLESS = os.environ.get("HEADLESS", "").strip().lower() in ("1", "true", "yes")

try:
    if sys.stdin.isatty() and not HEADLESS:
        bucle_teclado_interactivo()
    else:
        print(
            "Modo sin teclado CMD (HEADLESS o sin TTY): puente HTTP y serial siguen activos.\n"
            "  Para usar key> en consola: sin variable HEADLESS y ejecuta: python main.py\n"
            "  Ctrl+C para detener.\n",
            flush=True,
        )
        while True:
            time.sleep(60)
except KeyboardInterrupt:
    print("\nInterrumpido (Ctrl+C).", flush=True)
finally:
    try:
        if ser is not None:
            ser.close()
    except Exception:
        pass
