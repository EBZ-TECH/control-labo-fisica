(function () {
  "use strict";

  function resolveBridgeBase() {
    try {
      var qs = new URLSearchParams(window.location.search || "");
      var q = (qs.get("bridge") || "").trim().replace(/\/$/, "");
      if (q) return q;
    } catch (e) {}
    var fromBuild =
      typeof window.__BRIDGE_BASE__ !== "undefined"
        ? String(window.__BRIDGE_BASE__).trim().replace(/\/$/, "")
        : "";
    if (fromBuild) return fromBuild;
    var h = location.hostname || "";
    if (h === "localhost" || h === "127.0.0.1" || !h) {
      return "http://127.0.0.1:8765";
    }
    return "";
  }

  const BRIDGE = resolveBridgeBase();

  const firebaseConfig = {
    apiKey: "AIzaSyAFu_9SJW5WZ4zmugla1dskV5cukCfrp4Q",
    authDomain: "control-acceso-lab.firebaseapp.com",
    databaseURL: "https://control-acceso-lab-default-rtdb.firebaseio.com",
    projectId: "control-acceso-lab",
    storageBucket: "control-acceso-lab.firebasestorage.app",
    messagingSenderId: "981434543593",
    appId: "1:981434543593:web:c21e216822faba6c5eaf78",
  };

  firebase.initializeApp(firebaseConfig);
  const auth = firebase.auth();
  const db = firebase.database();

  function userIdFromEmail(email) {
    const normalized = String(email).trim().toLowerCase();
    return btoa(unescape(encodeURIComponent(normalized)))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  }

  function generarCodigoReserva() {
    const chars = "0123456789";
    let out = "";
    const cryptoObj = window.crypto || window.msCrypto;
    const buf = new Uint8Array(6);
    cryptoObj.getRandomValues(buf);
    for (let i = 0; i < 6; i++) {
      out += chars[buf[i] % chars.length];
    }
    return out;
  }

  function rolDesdeEmail(email) {
    const e = String(email || "").trim().toLowerCase();
    if (e === "admin@gmail.com") return "admin";
    return "student";
  }

  const views = {
    login: document.getElementById("view-login"),
    portal: document.getElementById("view-portal"),
    form: document.getElementById("view-form"),
    menu: document.getElementById("view-menu"),
  };

  function showView(name) {
    Object.keys(views).forEach((k) => {
      views[k].classList.toggle("hidden", k !== name);
    });
  }

  let currentUser = null;
  let currentRole = "student";
  let keypadContext = "menu";

  const loginForm = document.getElementById("login-form");
  const loginStatus = document.getElementById("login-status");
  const btnLogin = document.getElementById("btn-login");
  const portalEmail = document.getElementById("portal-email");
  const roleBadge = document.getElementById("role-badge");
  const cardForm = document.getElementById("card-form");
  const cardMenu = document.getElementById("card-menu");
  const portalDenied = document.getElementById("portal-denied");
  const btnLogout = document.getElementById("btn-logout");
  const btnFormBack = document.getElementById("btn-form-back");
  const btnMenuBack = document.getElementById("btn-menu-back");
  const menuStatus = document.getElementById("menu-status");
  const estadoSync = document.getElementById("estado-sync");
  const keypadEl = document.getElementById("keypad");

  function setLoginStatus(msg, kind) {
    loginStatus.textContent = msg || "";
    loginStatus.className = "status " + (kind || "");
  }

  function setMenuStatus(msg, kind) {
    menuStatus.textContent = msg || "";
    menuStatus.className = "status " + (kind || "");
  }

  function updatePortalUI() {
    if (!currentUser) return;
    portalEmail.textContent = currentUser.email || "";
    currentRole = rolDesdeEmail(currentUser.email);
    roleBadge.textContent = currentRole === "admin" ? "Administrador" : "Estudiante";
    roleBadge.classList.toggle("admin", currentRole === "admin");
    portalDenied.classList.add("hidden");
    portalDenied.textContent = "";
    cardMenu.classList.remove("disabled");
  }

  async function bridgeSession() {
    if (!BRIDGE) {
      throw new Error("sin_puente");
    }
    const body = JSON.stringify({
      email: currentUser ? currentUser.email : "",
      role: currentRole,
    });
    const r = await fetch(BRIDGE + "/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (!r.ok) throw new Error("Puente: /session " + r.status);
  }

  let bloqueoPollId = null;
  let lastBloqueoArduino = false;

  function setKeypadBloqueado(on) {
    keypadEl.querySelectorAll("button").forEach(function (btn) {
      btn.disabled = !!on;
    });
    keypadEl.classList.toggle("keypad-bloqueado", !!on);
  }

  function stopBloqueoPoll() {
    if (bloqueoPollId) {
      clearInterval(bloqueoPollId);
      bloqueoPollId = null;
    }
    lastBloqueoArduino = false;
  }

  async function syncEstadoArduino() {
    if (!BRIDGE) return;
    try {
      const r = await fetch(BRIDGE + "/status", { method: "GET" });
      if (!r.ok) return;
      const d = await r.json();
      const on = !!d.bloqueado;
      const modo = String(d.modo || "menu").toLowerCase();
      if (modo === "codigo") {
        keypadContext = "code";
      } else {
        keypadContext = "menu";
      }
      setKeypadBloqueado(on);
      if (on && !lastBloqueoArduino) {
        setMenuStatus("Sistema bloqueado. Sigue el LCD del Arduino.", "warn");
      }
      if (!on && lastBloqueoArduino) {
        setMenuStatus("", "");
      }
      lastBloqueoArduino = on;
      if (estadoSync) {
        if (on) {
          estadoSync.textContent = "Estado Arduino: bloqueado (sincronizado con el LCD).";
        } else if (modo === "codigo") {
          estadoSync.textContent = "Estado Arduino: ingreso de codigo (igual que el LCD).";
        } else {
          estadoSync.textContent = "Estado Arduino: menu principal (igual que el LCD).";
        }
      }
    } catch (_) {}
  }

  function startBloqueoPoll() {
    stopBloqueoPoll();
    syncEstadoArduino();
    bloqueoPollId = setInterval(syncEstadoArduino, 400);
  }

  async function bridgeKey(key) {
    if (!BRIDGE) {
      throw new Error("sin_puente");
    }
    const ctx = keypadContext === "code" ? "digit" : "menu";
    const body = JSON.stringify({ key, context: ctx });
    const r = await fetch(BRIDGE + "/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const data = await r.json().catch(() => ({}));
    if (r.status === 403 && data.bloqueado) {
      return { bloqueado: true };
    }
    if (!r.ok) throw new Error(data.error || "Puente: /key " + r.status);
    return data;
  }

  function buildKeypad() {
    keypadEl.innerHTML = "";
    const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];
    keys.forEach((k) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = k;
      b.addEventListener("click", async () => {
        try {
          const res = await bridgeKey(k);
          if (res.bloqueado) {
            setKeypadBloqueado(true);
            setMenuStatus("Sistema bloqueado. Sigue el LCD del Arduino.", "warn");
            return;
          }
          if (res.lcd === "usuario_invalido") {
            setMenuStatus(
              "LCD: USUARIO INVALIDO (historial no permitido para estudiante).",
              "err"
            );
            await syncEstadoArduino();
            return;
          }
          setMenuStatus("", "");
          await syncEstadoArduino();
        } catch (e) {
          console.error(e);
          setMenuStatus(
            !BRIDGE
              ? "Falta URL del puente: en Vercel define BRIDGE_PUBLIC_URL o abre ?bridge=https://tu-servicio"
              : "No hay puente. Ejecuta python main.py (8765) o revisa la URL del puente.",
            "err"
          );
        }
      });
      keypadEl.appendChild(b);
    });
  }

  auth.onAuthStateChanged((user) => {
    currentUser = user;
    if (user) {
      updatePortalUI();
      showView("portal");
    } else {
      showView("login");
    }
  });

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-pass").value;
    if (!email || !password) {
      setLoginStatus("Completa correo y contraseña.", "err");
      return;
    }
    btnLogin.disabled = true;
    setLoginStatus("Entrando…", "");
    try {
      await auth.signInWithEmailAndPassword(email, password);
      setLoginStatus("", "");
    } catch (err) {
      console.error(err);
      setLoginStatus(
        err.message || "No se pudo iniciar sesión. Revisa Auth en Firebase (correo/contraseña).",
        "err"
      );
    } finally {
      btnLogin.disabled = false;
    }
  });

  btnLogout.addEventListener("click", () => auth.signOut());

  cardForm.addEventListener("click", () => {
    showView("form");
  });

  cardMenu.addEventListener("click", () => {
    keypadContext = "menu";
    showView("menu");
    setMenuStatus("", "");
    bridgeSession()
      .then(() => {
        setMenuStatus("", "");
        startBloqueoPoll();
      })
      .catch(() => {
        setMenuStatus(
          !BRIDGE
            ? "Falta BRIDGE_PUBLIC_URL en el deploy o parámetro ?bridge= en la URL."
            : "No se pudo contactar el puente. Ejecuta python main.py o revisa CORS y la URL pública.",
          "err"
        );
      });
  });

  btnFormBack.addEventListener("click", () => {
    showView("portal");
    updatePortalUI();
  });

  btnMenuBack.addEventListener("click", () => {
    stopBloqueoPoll();
    setKeypadBloqueado(false);
    setMenuStatus("", "");
    if (estadoSync) estadoSync.textContent = "";
    showView("portal");
    updatePortalUI();
  });

  buildKeypad();

  /* ---------- Formulario reserva (Firebase RTDB) ---------- */
  const form = document.getElementById("reserva-form");
  const btn = document.getElementById("btn-enviar");
  const statusEl = document.getElementById("status");
  const codeBox = document.getElementById("codigo-generado");

  function setStatus(msg, kind) {
    statusEl.textContent = msg || "";
    statusEl.className = kind || "";
  }

  function showCode(code) {
    codeBox.textContent = "Código de reserva: " + code;
    codeBox.classList.add("visible");
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    codeBox.classList.remove("visible");
    codeBox.textContent = "";

    const nombre = document.getElementById("nombre").value.trim();
    const email = document.getElementById("email").value.trim();
    const fecha = document.getElementById("fecha").value;
    const hora_inicio = document.getElementById("hora_inicio").value;
    const tiempoRaw = document.getElementById("tiempo_min").value;
    const tiempo_min = parseInt(tiempoRaw, 10);

    if (!nombre || !email || !fecha || !hora_inicio || !Number.isFinite(tiempo_min) || tiempo_min < 1) {
      setStatus("Completa todos los campos correctamente.", "err");
      return;
    }

    const user_id = userIdFromEmail(email);
    const codigo = generarCodigoReserva();
    const reservaRef = db.ref("reservas").push();
    const ahora = new Date().toISOString();

    btn.disabled = true;
    setStatus("Guardando…", "");

    try {
      await db.ref("usuarios/" + user_id).update({
        nombre,
        email,
        actualizado_en: ahora,
      });

      await reservaRef.set({
        codigo,
        user_id,
        fecha,
        hora_inicio,
        tiempo_min,
        estado: "activo",
        creado_en: ahora,
      });

      setStatus("Reserva guardada correctamente.", "ok");
      showCode(codigo);
    } catch (err) {
      console.error(err);
      setStatus(
        "Error al guardar. Revisa la consola y las reglas de Firebase Realtime Database.",
        "err"
      );
    } finally {
      btn.disabled = false;
    }
  });
})();
