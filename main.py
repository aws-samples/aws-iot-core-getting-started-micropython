import os
import sys
import time
import ujson
import machine
import network
import ssl
from umqtt.simple import MQTTClient

#Enter your wifi SSID and password below.
wifi_ssid = "WIRELESS_SSID"
wifi_password = "WIRELESS_PASSWORD"

#Enter your AWS IoT endpoint. You can find it in the Settings page of
#your AWS IoT Core console. 
#https://docs.aws.amazon.com/iot/latest/developerguide/iot-connect-devices.html 
aws_endpoint = b'AWS_ENDPOINT.amazonaws.com'

#If you followed the blog, these names are already set.
# To validate the IoT endpoint, the Amazon Root CA cert is needed.
# You can get this from https://www.amazontrust.com/repository/AmazonRootCA1.pem
# This can also be downloaded when creating the certs for your device in the IoT Console
# For more details:
#   https://docs.aws.amazon.com/iot/latest/developerguide/server-authentication.html#server-authentication-certs
thing_name = "BlogThing"
client_id = "BlogClient"
private_key = "private.pem.key"
private_cert = "cert.pem.crt"
ca_cert = "AmazonRootCA1.pem"

#These are the topics we will subscribe to. We will publish updates to /update.
#We will subscribe to the /update/delta topic to look for changes in the device shadow.
topic_pub = "$aws/things/" + thing_name + "/shadow/update"
topic_sub = "$aws/things/" + thing_name + "/shadow/update/delta"

#Define pins for LED and light sensor. In this example we are using a FeatherS2.
#The sensor and LED are built into the board, and no external connections are required.
light_sensor = machine.ADC(machine.Pin(4))
light_sensor.atten(machine.ADC.ATTN_11DB)
led = machine.Pin(13, machine.Pin.OUT)
info = os.uname()

#Connect to the wireless network
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
if not wlan.isconnected():
    print('Connecting to network...')
    wlan.connect(wifi_ssid, wifi_password)
    while not wlan.isconnected():
        pass

    print('Connection successful')
    print('Network config:', wlan.ifconfig())

def connect_to_iot(mqtt_client):
    print("Connecting to AWS IoT...")
    mqtt_client.connect()
    print("Done")
    return mqtt_client

# used for micropython 1.23 and above
def mqtt_connect_new(client=client_id, endpoint=aws_endpoint, key=private_key, cert=private_cert, ca=ca_cert):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    # cert and key must be strings if using a file path.
    # If these are bytes (b""), then they are interpreted as the cert data
    ctx.load_cert_chain(cert, key)

    # to verify the IoT Endpoint's certificate is valid
    ctx.load_verify_locations(cafile=ca)
    ctx.verify_mode = ssl.CERT_REQUIRED

    mqtt = MQTTClient(client_id=client, server=endpoint, port=8883, keepalive=1200, ssl=ctx)
    return connect_to_iot(mqtt)

# used for micropython 1.22 and below
def mqtt_connect(client=client_id, endpoint=aws_endpoint):
    with open(private_key, 'r') as f:
        key = f.read()
    with open(private_cert, 'r') as f:
        cert = f.read()

    sslp = {"key": key, "cert": cert, "server_side": False}
    mqtt = MQTTClient(client_id=client, server=endpoint, port=8883, keepalive=1200, ssl=True, ssl_params=sslp)
    return connect_to_iot(mqtt)

def mqtt_publish(client, topic=topic_pub, message=''):
    print("Publishing message...")
    client.publish(topic, message)
    print(message)

def mqtt_subscribe(topic, msg):
    print("Message received...")
    message = ujson.loads(msg)
    print(topic, message)
    if message['state']['led']:
        led_state(message)
    print("Done")

def led_state(message):
    led.value(message['state']['led']['onboard'])

# determine micropython version
# change the connection implementation if 1.23+ due to a breaking change with ssl
# see: https://github.com/micropython/micropython-lib/pull/793
if sys.implementation.version[1] >= 23:
    mqtt_connect = mqtt_connect_new
else:
    mqtt_connect = mqtt_connect

#We use our helper function to connect to AWS IoT Core.
#The callback function mqtt_subscribe is what will be called if we 
#get a new message on topic_sub.
try:
    mqtt = mqtt_connect()
    mqtt.set_callback(mqtt_subscribe)
    mqtt.subscribe(topic_sub)
except:
    print("Unable to connect to MQTT.")


while True:
#Check for messages.
    try:
        mqtt.check_msg()
    except:
        print("Unable to check for messages.")

    mesg = ujson.dumps({
        "state":{
            "reported": {
                "device": {
                    "client": client_id,
                    "uptime": time.ticks_ms(),
                    "hardware": info[0],
                    "firmware": info[2]
                },
                "sensors": {
                    "light": light_sensor.read()
                },
                "led": {
                    "onboard": led.value()
                }
            }
        }
    })

#Using the message above, the device shadow is updated.
    try:
        mqtt_publish(client=mqtt, message=mesg)
    except:
        print("Unable to publish message.")

#Wait for 10 seconds before checking for messages and publishing a new update.
    print("Sleep for 10 seconds")
    time.sleep(10)