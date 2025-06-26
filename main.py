from machine import Pin, ADC, reset
import time
import network
from umqtt.simple import MQTTClient
import dht
import json

# Configuración de pines
SENSOR1_PIN = 5 # D1
SENSOR2_PIN = 4 # D2
SENSOR3_PIN = 14 # D5
SENSOR4_PIN = 12 # D6

RELAY1_PIN = 16  # D0
RELAY2_PIN = 0  # D3
RELAY3_PIN = 15  # D8

SENSOR_DHT22_PIN = 13  # D7

# Configuración WiFi
WIFI_SSID = "Fichas Ciber"
WIFI_PASS = ""

# Configuración MQTT
MQTT_BROKER = ""  # IP broker MQTT
MQTT_PORT = 1883
MQTT_USER = None  # Si requiere autenticación
MQTT_PASS = None

CLIENT_ID = "vista_hermosa"

TOPIC_PUB = b"info/" + CLIENT_ID
TOPIC_SUB = b"action/" + CLIENT_ID

# Variables globales
update_interval = 15 # segundos
last_update = 0

# Inicializar hardware

adc = ADC(0)

factor_escala = (2_200_000 + 220_000 + 100_000) / 100_000  # (R1 + R2+ R3) / R3 (2.2M + 220K + 100K)/100K

sensor1 = Pin(SENSOR1_PIN, Pin.IN, Pin.PULL_UP)
sensor2 = Pin(SENSOR2_PIN, Pin.IN, Pin.PULL_UP)
sensor3 = Pin(SENSOR3_PIN, Pin.IN, Pin.PULL_UP)
sensor4 = Pin(SENSOR4_PIN, Pin.IN, Pin.PULL_UP)

relay1 = Pin(RELAY1_PIN, Pin.OUT)
relay2 = Pin(RELAY2_PIN, Pin.OUT)
relay3 = Pin(RELAY3_PIN, Pin.OUT)

sensorDHT = dht.DHT22(Pin(SENSOR_DHT22_PIN))

def emergencia(pin):
    global last_update
    last_update = 0

def read_file():
    with open("ip.txt", 'r') as file:
        return file.read()
    
def write_file(data):
    with open("ip.txt","w") as file:
        file.write(data)

def connect_wifi():
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
        data = json.loads(msg)
        if "relay1" in data:
            relay1.value(data["relay1"])
        if "relay2" in data:
            relay2.value(data["relay2"])
        if "relay3" in data:
            relay3.value(data["relay3"])
        if "ip" in data:
            if data["ip"] != read_file():
                write_file(data["ip"])
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
    try:
        #sensorDHT.measure()
        #temp = sensorDHT.temperature()
        #hum = sensorDHT.humidity()
        volt = leer_voltaje()
        return {
            "Sensor0": not sensor1.value(),
            "Sensor1": not sensor2.value(),
            "Sensor2": not sensor3.value(),
            "Sensor3": not sensor4.value(),
            "Temperatura": 0,
            "Humedad": 0,
            "Bateria": volt,
            "relay1": bool(relay1.value()),
            "relay2": bool(relay2.value()),
            "relay3": bool(relay3.value()),
            "client_id": CLIENT_ID
        }
    except Exception as e:
        print("Error leyendo sensores:", e)
        return None

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
    global last_update, client, MQTT_BROKER
    MQTT_BROKER = read_file()
    connect_wifi()
    relay1.value(0)  # Iniciar con relé apagado
    relay2.value(0)
    relay3.value(0)
    sensor1.irq(trigger=Pin.IRQ_RISING, handler=emergencia) # Activar las interrupciones
    sensor2.irq(trigger=Pin.IRQ_RISING, handler=emergencia)
    sensor3.irq(trigger=Pin.IRQ_RISING, handler=emergencia)
    sensor4.irq(trigger=Pin.IRQ_RISING, handler=emergencia)
    
    try:
        client = connect_mqtt()
        #last_update = 0
        while True:
            client.check_msg()  # Verificar mensajes entrantes
            current_time = time.time()
            if current_time - last_update >= update_interval:
                publish_sensor_data()
                last_update = current_time
            time.sleep(0.1)
    except Exception as e:
        print("Error en el bucle principal:", e)
        reset()

if __name__ == "__main__":
    main()