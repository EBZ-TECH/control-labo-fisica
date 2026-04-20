#include <LiquidCrystal.h>
#include <stdio.h>

// LCD (RS=12, E=11, D4-D7 = 5,4,3,2)
LiquidCrystal lcd(12, 11, 5, 4, 3, 2);

// LED externo "puerta" (no es el L del pin 13): cambia LED_PUERTA si cableas otro D6..D10.
// Montaje A (recomendado): D? -> resistencia 220-330Ω -> patas LED (LARGA +) -> (CORTA -) -> GND
// Montaje B (tutorías): 5V -> resistencia -> LED -> pin (cátodo al pin). Si usas B, pon LED_EXT_ON_LEVEL en LOW.
const int LED_PUERTA = 6;
const uint8_t LED_EXT_ON_LEVEL = HIGH;

static void ledExterno(bool encendido) {
  const uint8_t nivel = encendido ? LED_EXT_ON_LEVEL : (LED_EXT_ON_LEVEL == HIGH ? LOW : HIGH);
  digitalWrite(LED_PUERTA, nivel);
}

static void ledPuertaOn() {
  ledExterno(true);
  digitalWrite(LED_BUILTIN, HIGH);
}

static void ledPuertaOff() {
  ledExterno(false);
  digitalWrite(LED_BUILTIN, LOW);
}

// Simulación de keypad por serial (PC / Python)
#define NO_KEY '\0'

char ultimaTecla = NO_KEY;

String codigo = "";
bool ingresando = false;

const unsigned long SERIAL_RESPONSE_TIMEOUT_MS = 15000;
const unsigned long BLOQUEO_MS = 120000UL;
const byte MAX_REGISTROS = 5;

String registros[MAX_REGISTROS];
byte registrosCount = 0;
byte registrosStart = 0;

byte intentosFallidos = 0;
bool bloqueado = false;
unsigned long bloqueoFinMs = 0;

void mostrarMenu();
void mostrarPantallaIngreso();
void mostrarHistorial();
void enviarCodigo(String cod);
void mostrarResultado(String l1, String l2);
bool esDigito(char c);
bool leerLineaSerial(String &out, unsigned long timeoutMs);
void guardarRegistro(String cod, String estado);
void actualizarIntentos(bool exito);
void activarBloqueo();
bool gestionarBloqueo();
char pollSerialInput();
void notificarPcUI(const char* modo);

void setup() {
  Serial.begin(9600);
  delay(1000);
  Serial.setTimeout(100);

  pinMode(LED_PUERTA, OUTPUT);
  pinMode(LED_BUILTIN, OUTPUT);
  ledPuertaOff();

  lcd.begin(16, 2);

  lcd.setCursor(0, 0);
  lcd.print("Sistema listo");
  delay(1500);
  mostrarMenu();

  // 2 parpadeos: LED L (pin 13) + LED externo en LED_PUERTA. Si solo parpadea L, revisa LED_EXT_ON_LEVEL y el cable del externo.
  for (byte i = 0; i < 2; i++) {
    ledPuertaOn();
    delay(150);
    ledPuertaOff();
    delay(150);
  }
}

void mostrarMenu() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("1:Ingresar 2:Reg");
  lcd.setCursor(0, 1);
  lcd.print("Seleccione op");
  notificarPcUI("menu");
}

void mostrarPantallaIngreso() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Digite codigo:");
  lcd.setCursor(0, 1);
  notificarPcUI("codigo");
}

void loop() {

  if (gestionarBloqueo()) return;

  char tecla = pollSerialInput();

  if (!tecla || tecla == ultimaTecla) return;

  ultimaTecla = tecla;

  if (!ingresando && tecla == '1') {
    ingresando = true;
    codigo = "";
    mostrarPantallaIngreso();
    delay(200);
    ultimaTecla = NO_KEY;
    return;
  }

  if (!ingresando && tecla == '2') {
    mostrarHistorial();
    delay(200);
    ultimaTecla = NO_KEY;
    return;
  }

  if (!ingresando) return;

  if (tecla == '*') {
    codigo = "";
    mostrarPantallaIngreso();
  } else if (tecla == '#') {
    if (codigo.length() == 6) {
      enviarCodigo(codigo);
      ingresando = false;
    } else {
      mostrarResultado("CODIGO", "6 DIGITOS");
      codigo = "";
      mostrarPantallaIngreso();
    }
  } else if (esDigito(tecla) && codigo.length() < 6) {
    codigo += tecla;
    lcd.print(tecla);
  }

  delay(200);
  ultimaTecla = NO_KEY;
}

/**
 * Lee una línea desde el PC. Si es comando !INVALID_USER, muestra en LCD y no devuelve tecla.
 * Si no, devuelve el primer carácter (compatible con teclas enviadas como "5\n").
 */
char pollSerialInput() {
  static String buffer = "";

  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      buffer.trim();
      if (buffer.length() == 0) {
        buffer = "";
        continue;
      }
      if (buffer.startsWith("!INVALID")) {
        mostrarResultado("USUARIO", "INVALIDO");
        buffer = "";
        return NO_KEY;
      }
      char tecla = buffer.charAt(0);
      buffer = "";
      return tecla;
    } else if (c != '\r') {
      buffer += c;
    }
  }

  return NO_KEY;
}

void enviarCodigo(String cod) {

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Enviando...");
  lcd.setCursor(0, 1);
  lcd.print(cod);

  while (Serial.available() > 0) Serial.read();

  Serial.println(cod);
  Serial.flush();

  String respuesta;

  if (leerLineaSerial(respuesta, SERIAL_RESPONSE_TIMEOUT_MS)) {

    respuesta.trim();

    if (respuesta == "OK") {
      guardarRegistro(cod, "OK");
      actualizarIntentos(true);
      mostrarResultado("ACCESO", "PERMITIDO");
      return;
    }

    if (respuesta == "DENEGADO") {
      guardarRegistro(cod, "DENEGADO");
      actualizarIntentos(false);
      mostrarResultado("ACCESO", "DENEGADO");
      return;
    }

    if (respuesta == "INVALIDO") {
      guardarRegistro(cod, "INVALIDO");
      actualizarIntentos(false);
      mostrarResultado("CODIGO", "INVALIDO");
      return;
    }

    mostrarResultado("RESPUESTA", respuesta.substring(0, 16));
    return;
  }

  mostrarResultado("SIN RESPUESTA", "ERROR");
}

void mostrarResultado(String l1, String l2) {
  const bool accesoOk = (l1 == "ACCESO" && l2 == "PERMITIDO");
  if (accesoOk) {
    ledPuertaOn();
  }

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(l1);
  lcd.setCursor(0, 1);
  lcd.print(l2);
  delay(2500);

  if (accesoOk) {
    ledPuertaOff();
  }

  mostrarMenu();
}

bool esDigito(char c) {
  return c >= '0' && c <= '9';
}

bool leerLineaSerial(String &out, unsigned long timeoutMs) {

  out = "";
  unsigned long inicio = millis();

  while (millis() - inicio < timeoutMs) {

    while (Serial.available()) {
      char ch = Serial.read();

      if (ch == '\n') {
        out.trim();
        return true;
      }

      if (ch != '\r') out += ch;
    }

    delay(5);
  }

  out.trim();
  return false;
}

void guardarRegistro(String cod, String estado) {

  String item = cod + " " + estado;

  if (registrosCount < MAX_REGISTROS) {
    registros[(registrosStart + registrosCount) % MAX_REGISTROS] = item;
    registrosCount++;
  } else {
    registros[registrosStart] = item;
    registrosStart = (registrosStart + 1) % MAX_REGISTROS;
  }
}

void actualizarIntentos(bool exito) {

  if (exito) {
    intentosFallidos = 0;
    return;
  }

  intentosFallidos++;

  if (intentosFallidos >= 3) activarBloqueo();
}

void notificarPcUI(const char* modo) {
  Serial.print("!UI:");
  Serial.println(modo);
  Serial.flush();
}

void notificarPcBloqueo(bool activo) {
  if (activo) {
    Serial.println("!BLOQUEO_ON");
  } else {
    Serial.println("!BLOQUEO_OFF");
  }
  Serial.flush();
}

void activarBloqueo() {
  bloqueado = true;
  bloqueoFinMs = millis() + BLOQUEO_MS;
  ingresando = false;
  codigo = "";
  notificarPcBloqueo(true);
  notificarPcUI("menu");
}

bool gestionarBloqueo() {

  if (!bloqueado) return false;

  long restante = bloqueoFinMs - millis();

  if (restante <= 0) {
    bloqueado = false;
    intentosFallidos = 0;
    notificarPcBloqueo(false);
    mostrarResultado("BLOQUEO", "FINALIZADO");
    return false;
  }

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("BLOQUEADO");

  unsigned long restMs = (unsigned long)restante;
  unsigned long totalSeg = restMs / 1000UL;
  unsigned long minutos = totalSeg / 60UL;
  unsigned long segundos = totalSeg % 60UL;

  lcd.setCursor(0, 1);
  char tiempo[10];
  snprintf(tiempo, sizeof(tiempo), "%02lu:%02lu", minutos, segundos);
  lcd.print(tiempo);

  delay(1000);

  return true;
}

void mostrarHistorial() {

  if (registrosCount == 0) {
    mostrarResultado("SIN DATOS", "");
    return;
  }

  for (int i = 0; i < registrosCount; i++) {

    int idx = (registrosStart + i) % MAX_REGISTROS;

    lcd.clear();
    lcd.print(registros[idx].substring(0, 16));
    delay(2000);
  }

  mostrarMenu();
}
