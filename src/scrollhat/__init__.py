import json
import time
from threading import Thread

import paho.mqtt.client as mqtt
import scrollphathd
from gpiozero import Button

machine_state = {"status": "off"}
shot_state = {"active": False}


def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
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


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect("10.0.1.178", 1883, 60)

t2 = Thread(target=client.loop_forever)
t2.start()


scrollphathd.set_brightness(0.5)
width, height = 17, 7

button_map = {
    5: ("A", 0, 0),  # Top Left
    6: ("B", 0, 6),  # Bottom Left
    16: ("X", 16, 0),  # Top Right
    24: ("Y", 16, 7),  # Buttom Right
}

button_a = Button(5)
button_b = Button(6)
button_x = Button(16)
button_y = Button(24)

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


def main() -> None:

    try:
        button_a.when_pressed = pressed
        button_b.when_pressed = pressed
        button_x.when_pressed = pressed
        button_y.when_pressed = pressed

        while True:
            scrollphathd.clear()
            if machine_state == {}:
                print("Waiting for machine state...")

            if shot_state["active"]:
                render_shot()
            elif machine_state["status"] in {"heating", "ready"}:
                render_heating()
            else:
                scrollphathd.clear()
                scrollphathd.show()
                # empty state
                continue
            scrollphathd.show()
            time.sleep(1.0 / 60.0)

    except KeyboardInterrupt:
        button_a.close()
        button_b.close()
        button_x.close()
        button_y.close()


t = Thread(target=main)
t.start()
