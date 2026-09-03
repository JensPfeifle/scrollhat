import json
import signal
import time
from threading import Event

import paho.mqtt.client as mqtt
import scrollphathd
from gpiozero import Button

MQTT_HOST = "10.0.1.178"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

machine_state = {"status": "off"}
shot_state = {"active": False}

# Set by SIGTERM/SIGINT so the render loop can unwind and blank the display.
stop = Event()


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected with result code " + str(reason_code))
    client.subscribe("marax/#")


def on_message(client, userdata, msg):
    global machine_state, shot_state
    print(f"Topic: {msg.topic} | Message: {msg.payload.decode()}")
    if msg.topic == "marax/machine":
        payload = json.loads(msg.payload.decode())
        print(payload)
        machine_state = payload

    if msg.topic == "marax/shot":
        payload = json.loads(msg.payload.decode())
        print(payload)
        shot_state = payload


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

width, height = 17, 7

button_map = {
    5: ("A", 0, 0),  # Top Left
    6: ("B", 0, 6),  # Bottom Left
    16: ("X", 16, 0),  # Top Right
    24: ("Y", 16, 7),  # Buttom Right
}

splash_origin = (0, 0)

state = "off"
temperature = 0.0
shot_start: time.time or None = None
shot_end: time.time or None = None


def pressed(button):
    button_name, x, y = button_map[button.pin.number]
    if button_name == "A":
        print("Off")
        client.publish("marax/control", json.dumps({"state": "off"}))
    if button_name == "B":
        print("Heating...")
        client.publish("marax/control", json.dumps({"state": "on"}))


def digit_square(brightness, x=0, y=0, value=0):
    value = int(value)
    if value == 0:
        return
    if value == 1:
        scrollphathd.fill(brightness, x, y, width=1, height=1)
    if value == 2:
        scrollphathd.fill(brightness, x, y, width=2, height=1)
    if value == 3:
        scrollphathd.fill(brightness, x, y, width=3, height=1)
    if value == 4:
        scrollphathd.fill(brightness, x, y, width=3, height=1)
        scrollphathd.fill(brightness, x, y + 1, width=1, height=1)
    if value == 5:
        scrollphathd.fill(brightness, x, y, width=3, height=1)
        scrollphathd.fill(brightness, x, y + 1, width=2, height=1)
    if value == 6:
        scrollphathd.fill(brightness, x, y, width=3, height=2)
    if value == 7:
        scrollphathd.fill(brightness, x, y, width=3, height=2)
        scrollphathd.fill(brightness, x, y + 2, width=1, height=1)
    if value == 8:
        scrollphathd.fill(brightness, x, y, width=3, height=2)
        scrollphathd.fill(brightness, x, y + 2, width=2, height=1)
    if value == 9:
        scrollphathd.fill(brightness, x, y, width=3, height=3)


def render_heating():
    temperature = int(machine_state["brew_temp"])
    tens = temperature // 10
    ones = temperature % 10
    digit_square(1.0, value=tens)
    digit_square(1.0, x=5, value=ones)

    progress_width = int(temperature / 91 * 17)

    scrollphathd.fill(1.0, 0, 4, width=progress_width, height=4)
    if int(ones) % 2 == 0:
        scrollphathd.fill(0.5, progress_width, 4, width=1, height=4)


def render_shot():
    duration = shot_state["duration"]
    scrollphathd.write_string(f":{duration:02d}", x=1)


def request_stop(signum, frame):
    print(f"Received signal {signum}, shutting down")
    stop.set()


def main() -> None:
    # systemd stops the unit with SIGTERM, so both signals have to unwind cleanly.
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
    # loop_start runs the network loop on a daemon thread, so a failure to stop
    # it cannot keep the process alive past shutdown.
    client.loop_start()

    scrollphathd.set_brightness(0.5)

    buttons = [Button(pin) for pin in button_map]
    for button in buttons:
        button.when_pressed = pressed

    try:
        while not stop.is_set():
            scrollphathd.clear()
            if machine_state == {}:
                print("Waiting for machine state...")

            if shot_state["active"]:
                render_shot()
            elif machine_state["status"] in {"heating", "ready"}:
                render_heating()
            # any other status leaves the display blank

            scrollphathd.show()
            # Doubles as the frame delay and wakes immediately on a signal.
            stop.wait(1.0 / 60.0)
    finally:
        for button in buttons:
            button.close()
        client.loop_stop()
        client.disconnect()
        scrollphathd.clear()
        scrollphathd.show()
