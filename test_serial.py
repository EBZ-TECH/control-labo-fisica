import serial

ser = serial.Serial("COM6", 9600)

print("Prueba activa...", flush=True)

while True:
    if ser.in_waiting:
        data = ser.readline().decode("utf-8", errors="ignore").strip()
        print("Recibido:", data, flush=True)

        ser.write(b"OK\n")  # RESPUESTA FORZADA
        ser.flush()