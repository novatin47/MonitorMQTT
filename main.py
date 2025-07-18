from machine import Pin, ADC, reset, freq
import time
import network
from umqtt.simple import MQTTClient
import dht
import usocket as socket
import json
from micropython import mem_info
import gc
freq(160000000)
print(mem_info())

# Configuración de pines
SENSOR1_PIN = 5 # D1
SENSOR2_PIN = 4 # D2
SENSOR3_PIN = 14 # D5

RESET_PIN = 12 # D6

RELAY1_PIN = 16  # D0
RELAY2_PIN = 0  # D3
RELAY3_PIN = 15  # D8

SENSOR_DHT22_PIN = 13  # D7

# Configuración WiFi
WIFI_SSID = ""
WIFI_PASS = ""

# Configuración MQTT
MQTT_BROKER = ""  # IP broker MQTT
MQTT_PORT = 1883
MQTT_USER = None  # Si requiere autenticación
MQTT_PASS = None

CLIENT_ID = ""

TOPIC_PUB = ""
TOPIC_SUB = ""

# Variables globales
update_interval = 15 # segundos
last_update = 0
send_data_config = False
# Inicializar hardware

adc = ADC(0)

factor_escala = (2_200_000 + 220_000 + 100_000) / 100_000  # (R1 + R2+ R3) / R3 (2.2M + 220K + 100K)/100K

sensor1 = Pin(SENSOR1_PIN, Pin.IN, Pin.PULL_UP)
sensor2 = Pin(SENSOR2_PIN, Pin.IN, Pin.PULL_UP)
sensor3 = Pin(SENSOR3_PIN, Pin.IN, Pin.PULL_UP)
reset_factory = Pin(RESET_PIN, Pin.IN, Pin.PULL_UP)

relay1 = Pin(RELAY1_PIN, Pin.OUT)
relay2 = Pin(RELAY2_PIN, Pin.OUT)
relay3 = Pin(RELAY3_PIN, Pin.OUT)

sensorDHT = dht.DHT22(Pin(SENSOR_DHT22_PIN))

def unquote(string):
    import binascii
    parts = string.split('%')
    result = [parts[0]]
    for part in parts[1:]:
        if len(part) >= 2:
            hex_code = part[:2]
            try:
                decoded = binascii.unhexlify(hex_code).decode('latin-1')
                result.append(decoded + part[2:])
            except:
                result.append('%' + part)
        else:
            result.append('%' + part)
    return ''.join(result)

def emergencia(pin):
    global last_update
    last_update = 0

def read_file():
    with open("config.txt", 'r') as file:
        return json.loads(file.read())
    
def write_file(data):
    with open("config.txt","w") as file:
        json.dump(data, file)

def connect_wifi():
    if WIFI_SSID == "test":
        print("Modo estacion desactivado...")
        sta_if = network.WLAN(network.AP_IF)
        print("Modo ap activado...")
        sta_if.active(True)
        sta_if.ifconfig(('192.168.1.254', '255.255.255.0', '192.168.1.254', '8.8.8.8'))
        sta_if.config(essid='Monitor', channel=6, authmode=0)
        print("Servidor activado")
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.bind(('',80))
        servidor.listen(2)
        while 1:
            try:
                conn, addr = servidor.accept()
                request = conn.recv(1024).decode('utf-8')
                if 'GET /?' in request:
                    query = request.split('GET /?', 1)[1].split(' HTTP')[0]
                    params = {}
                    for pair in query.split('&'):
                        if '=' in pair:
                            key, value = pair.split('=', 1)
                            params[key] = unquote(value)  # Decodifica caracteres especiales (ej: %20 → espacio)
                    print(params)
                    data_actual = read_file()
                    data_actual.update(params)
                    write_file(data_actual)
                    conn.send('HTTP/1.1 200 OK\nContent-Type: application/json\n\n')
                    conn.send(json.dumps(data_actual))
                    conn.close()
                elif 'GET /ok' in request:
                    conn.send('HTTP/1.1 200 OK\n\nOK')
                    conn.close()
                    reset()
                else:
                    conn.send('HTTP/1.1 200 OK\nContent-Type: application/json\n\n')
                    conn.send(json.dumps(read_file()))
                    conn.close()
            except Exception as ex:
                print("Error en la conexion del cliente ",ex)
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print("Conectando a WiFi...")
        sta_if.active(True)
        sta_if.connect(WIFI_SSID, WIFI_PASS)
        while not sta_if.isconnected():
            time.sleep(0.5)
            print(".", end="")
    print("\nWiFi conectado!")
    print("IP:", sta_if.ifconfig()[0])
    
def leer_voltaje():
    valor = adc.read()
    voltaje_medido = (valor * 1.0) / 1023
    voltaje_real = voltaje_medido * factor_escala  # Ajuste para el divisor
    return voltaje_real

def mqtt_callback(topic, msg):
    print("Mensaje recibido:", topic, msg)
    try:
        global send_data_config
        data = json.loads(msg)
        actual = read_file()
        if "relay1" in data:
            relay1.value(data["relay1"])
        if "relay2" in data:
            relay2.value(data["relay2"])
        if "relay3" in data:
            relay3.value(data["relay3"])
        if "broker" in data or "id" in data or "essid" in data or "password" in data:
            #actual["broker"] = data["broker"] if data["broker"] != actual.get("broker","") else actual.get("broker","")
            actual.update(data)
            write_file(actual)
            send_data_config = True
        if "config" in data:
            send_data_config = True
        if "reset" in data:
            reset()
        publish_sensor_data()
    except ValueError as e:
        print("Error procesando mensaje MQTT:", e)

def connect_mqtt():
    client = MQTTClient(
        CLIENT_ID,
        MQTT_BROKER,
        port=MQTT_PORT,
        user=MQTT_USER,
        password=MQTT_PASS
    )
    client.set_callback(mqtt_callback)
    client.connect()
    client.subscribe(TOPIC_SUB)
    print("Conectado al broker MQTT")
    return client

def read_sensors():
    temp = 0
    hum = 0
    try:
        sensorDHT.measure()
        temp = sensorDHT.temperature()
        hum = sensorDHT.humidity()
    except Exception as e:
        print("Error leyendo sensor dht:", e)

    volt = leer_voltaje()
    data = {
        "Sensor0": not sensor1.value(),
        "Sensor1": not sensor2.value(),
        "Sensor2": not sensor3.value(),
        "Temperatura": temp,
        "Humedad": hum,
        "Bateria": float(f"{volt:.2f}"),
        "relay1": bool(relay1.value()),
        "relay2": bool(relay2.value()),
        "relay3": bool(relay3.value()),
        "client_id": CLIENT_ID
    }

    global send_data_config
    if send_data_config:
        send_data_config = False
        data["config"] = read_file()
        

    return data

def publish_sensor_data():
    global client
    sensor_data = read_sensors()
    if sensor_data:
        try:
            client.publish(TOPIC_PUB, json.dumps(sensor_data))
            print("Datos publicados:", sensor_data)
        except Exception as e:
            print("Error publicando datos:", e)
            client = connect_mqtt()

def main():
    global last_update, client, MQTT_BROKER, WIFI_SSID, WIFI_PASS, CLIENT_ID, TOPIC_PUB, TOPIC_SUB
    config = read_file()
    WIFI_SSID = config.get("essid", "test") if reset_factory.value() else "test"
    WIFI_PASS = config.get("password", "")
    CLIENT_ID = config.get("id", "test")
    MQTT_BROKER = config.get("broker", "192.168.1.254")
    TOPIC_PUB = b"info/" + CLIENT_ID
    TOPIC_SUB = b"action/" + CLIENT_ID
    config = None
    connect_wifi()
    relay1.value(0)  # Iniciar con relé apagado
    relay2.value(0)
    relay3.value(0)
    sensor1.irq(trigger=Pin.IRQ_RISING, handler=emergencia) # Activar las interrupciones
    sensor2.irq(trigger=Pin.IRQ_RISING, handler=emergencia)
    sensor3.irq(trigger=Pin.IRQ_RISING, handler=emergencia)
    
    try:
        client = connect_mqtt()
        #last_update = 0
        while True:
            client.check_msg()  # Verificar mensajes entrantes
            current_time = time.time()
            if current_time - last_update >= update_interval:
                publish_sensor_data()
                last_update = current_time
            gc.collect()
            time.sleep(0.1)
    except Exception as e:
        print("Error en el bucle principal:", e)
        reset()

if __name__ == "__main__":
    main()